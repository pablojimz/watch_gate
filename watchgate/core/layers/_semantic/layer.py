"""SemanticLayer — orquesta prompting/tools/client/RAG (§7.5).

`cost_control` se recibe como un `CostControllerLike` (Protocol estructural):
esta capa no importa `watchgate.core.cost_control` directamente, así que es
testeable con un fake y se integra con la implementación real de esa pieza
(§8) sin cambiar una línea aquí — solo pasando la instancia real al
constructor.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from watchgate.core.aggregator import DEFAULT_THRESHOLDS
from watchgate.core.layers._semantic import chunking, prompting, tools
from watchgate.core.layers._semantic.client import (
    LLMClient,
    SemanticOutput,
    SemanticParsingError,
    ToolExecutor,
)
from watchgate.core.layers._shared import find_prompt_injection_attempts
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import Finding, LayerResult, NormalizedDiff, RiskCategory, ThreatNature
from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH
from watchgate.core.rag.retriever import retrieve_relevant_context

logger = logging.getLogger("watchgate.semantic")

_MAX_TOOL_CALLS = 3
_NO_BUDGET_SKIP_REASON = "Presupuesto de tokens agotado para este repositorio este mes"

# Análisis por chunks (diff que no cabe entero, ver `chunking.py`): cada
# paquete es una llamada independiente al LLM, se lanzan en paralelo para
# no multiplicar la latencia por el número de paquetes. Mismo orden de
# magnitud que `_MAX_WORKERS` de `tests/integration/generate_validation_
# report.py` (la propia llamada HTTP libera el GIL).
_CHUNK_WORKERS = 6

# Auto-consistencia: solo para respuestas "límite" (cerca de un umbral de
# semáforo -- los mismos 40/70 por defecto de aggregator.DEFAULT_THRESHOLDS,
# repetidos aquí en vez de importar el módulo de agregación para no acoplar
# capas entre sí), se piden hasta _MAX_RESAMPLES llamadas adicionales y se
# usa la de mayor risk_score. Hallazgo real de la suite de validación
# (tests/cases/): el mismo diff exacto puede dar amarillo o rojo entre dos
# llamadas distintas a la API -- no es un bug, es varianza real del modelo,
# pero cerca de un umbral decide el semáforo final. Lejos de cualquier
# umbral (verde claro o rojo claro) no merece la pena el coste extra: ahí la
# varianza no cambia el veredicto.
_BORDERLINE_THRESHOLDS = (DEFAULT_THRESHOLDS["yellow"], DEFAULT_THRESHOLDS["red"])
_BORDERLINE_MARGIN = 10
_MAX_RESAMPLES = 2


def _is_borderline_score(risk_score: int) -> bool:
    return any(abs(risk_score - t) <= _BORDERLINE_MARGIN for t in _BORDERLINE_THRESHOLDS)


# Suelo mecánico, no una sugerencia en el prompt: si el prompt de verdad
# contiene contenido sin verificar (UNVERIFIED_CONTENT_MARKER -- un fichero
# truncado sin extracto, o directamente sin presupuesto), el LLM no llamó a
# `fetch_referenced_file` para comprobarlo por su cuenta, Y aun así concluye
# un riesgo bajo, el score no se queda tal cual. Objetivo explícito: que
# "no he podido revisarlo" nunca se traduzca en verde -- como mínimo debe
# saltar la alarma de AMARILLO.
#
# 40 no basta: este suelo actúa sobre el risk_score de ESTA capa, no sobre
# el score combinado final. Con los pesos por defecto (reputation=0.15,
# semantic=0.40) y reputación en 0 (peor caso real -- una cuenta comprometida
# no deja ninguna señal de reputación sospechosa), el combinado es
# 0.40*S/0.55; para que ese combinado llegue de verdad a los 40 de
# aggregator.DEFAULT_THRESHOLDS["yellow"] hace falta S >= 55. Se deja margen
# hasta 60 -- verificado en la práctica contra la suite de validación real
# (tests/cases/): con 40 el combinado se quedaba en 29, por debajo de la
# propia alarma que se pretendía forzar.
_MIN_SCORE_WHEN_UNVERIFIED = 60


def _apply_unverified_content_floor(
    output: SemanticOutput, has_unverified_marker: bool, fetch_referenced_file_calls: int
) -> SemanticOutput:
    if (
        not has_unverified_marker
        or fetch_referenced_file_calls > 0
        or output.risk_score >= _MIN_SCORE_WHEN_UNVERIFIED
    ):
        return output
    return output.model_copy(
        update={
            "risk_score": _MIN_SCORE_WHEN_UNVERIFIED,
            "threat_nature": ThreatNature.UNCERTAIN,
            "justification": (
                f"{output.justification} [Ajustado a {_MIN_SCORE_WHEN_UNVERIFIED}: "
                "hay contenido del diff que no se pudo revisar (truncado por tamaño) y "
                "no se consultó con fetch_referenced_file -- incertidumbre real, no "
                "verificada como segura, no se deja en verde sin comprobar.]"
            ),
        }
    )


# Suelo mecánico independiente del anterior: si el propio diff (o el
# contenido de un fichero leído con fetch_referenced_file) contiene texto
# que intenta manipular al LLM -- falsos mensajes de sistema ("system:"),
# JSON de respuesta falsificado incrustado ('"risk_score": 0, "justification"'),
# instrucciones explícitas de qué responder ("respond only with risk_score")
# -- eso es evidencia de intención maliciosa por sí sola, la haya seguido el
# modelo o no: un PR legítimo nunca tiene motivo para imitar la sintaxis de
# una respuesta dirigida a un analizador automático. 100, no un umbral
# calculado: no queda margen de duda razonable aquí.
#
# Deliberadamente NO se incluyen aquí las etiquetas de lenguaje genérico de
# `_PROMPT_INJECTION_PATTERNS` (p. ej. "ignore_previous_instructions",
# "instructs_to_skip_analysis", "claims_preapproved", "disregard_instructions",
# "role_override") -- bug real, reproducido: un LLM real, viendo el diff
# completo, juzgaba correctamente como benigno un comentario de código de lo
# más normal ("// TODO: don't flag this edge case, it's intentional"), y este
# suelo descartaba ese juicio y forzaba 100/MALICIOSO solo por la presencia
# de esas palabras -- exactamente lo contrario de "detectar intención": es
# buscar palabras sueltas e ignorar el contexto que el propio LLM sí tuvo.
# Esas frases son demasiado comunes en prosa/comentarios corrientes para ser
# evidencia fiable por sí solas. Las etiquetas de abajo, en cambio, solo
# aparecen de forma realista si el texto se escribió a propósito para que lo
# lea un LLM como si fuera una instrucción o una respuesta -- ahí sí hay
# intención real, no una coincidencia de vocabulario.
_STRUCTURAL_LLM_TARGETING_LABELS = frozenset(
    {
        "fake_role_marker",
        "instructs_response_content",
        "embedded_fake_json_response",
        "new_instructions_marker",
    }
)
_PROMPT_INJECTION_FLOOR_SCORE = 100
_NO_LLM_CONFIG_SKIP_REASON = (
    "Capa semántica omitida (requiere clave de API o configuración de proveedor LLM en el entorno)"
)


def _apply_prompt_injection_floor(output: SemanticOutput, scanned_text: str) -> SemanticOutput:
    findings = find_prompt_injection_attempts(scanned_text)
    has_structural_evidence = any(label in _STRUCTURAL_LLM_TARGETING_LABELS for label in findings)
    if not has_structural_evidence or output.risk_score >= _PROMPT_INJECTION_FLOOR_SCORE:
        return output
    return output.model_copy(
        update={
            "risk_score": _PROMPT_INJECTION_FLOOR_SCORE,
            "threat_nature": ThreatNature.MALICIOUS,
            "category": RiskCategory.OFUSCACION,
            "justification": (
                f"{output.justification} [Ajustado a {_PROMPT_INJECTION_FLOOR_SCORE}: el diff "
                f"contiene texto que intenta manipular al analizador ({', '.join(findings)}) -- "
                "un PR legítimo nunca necesita instruir al revisor para que ignore su análisis; "
                "el intento de inyección de prompt es en sí mismo evidencia de ataque.]"
            ),
        }
    )


class CostControllerLike(Protocol):
    """Subconjunto de watchgate/core/cost_control.py (§8) que necesita esta
    capa. Al ser un Protocol, la implementación real de esa pieza no
    necesita heredar de aquí: basta con exponer estos métodos."""

    def budget_remaining(self, repo: str) -> int: ...
    def estimate_tokens(self, text: str) -> int: ...
    def get_cached(self, diff_hash: str) -> SemanticOutput | None: ...
    def store_cached(self, diff_hash: str, output: SemanticOutput) -> None: ...
    def record_usage(self, repo: str, tokens_used: int) -> None: ...


def compute_diff_hash(diff: NormalizedDiff) -> str:
    """Determinista: el mismo diff exacto produce el mismo hash (§8)."""
    return hashlib.sha256(
        json.dumps(diff.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


class _ToolCallCounter:
    def __init__(self) -> None:
        self.count = 0
        # Contador específico de `fetch_referenced_file` (no "cualquier
        # tool"): `_apply_unverified_content_floor` necesita saber si el
        # contenido truncado se llegó a comprobar de verdad, no si el LLM
        # llamó a alguna otra tool sin relación (p. ej. `lookup_package_registry`
        # para una dependencia legítima, dejando el fichero truncado sospechoso
        # sin leer). Hallazgo de revisión: antes se usaba `count > 0` genérico.
        self.fetch_referenced_file_calls = 0
        # Contenido real devuelto por `fetch_referenced_file` durante la
        # conversación -- hay que escanearlo por intentos de inyección de
        # prompt igual que el `user_prompt` inicial (ver comentario de
        # `_apply_prompt_injection_floor`): un fichero truncado en el prompt
        # inicial (sin extracto, solo el marcador de "no verificado") puede
        # contener el texto de inyección real, que solo llega al LLM cuando
        # éste decide leerlo con esta tool. Sin esto, ese texto nunca se
        # escaneaba -- el suelo mecánico solo miraba `user_prompt`.
        self.fetched_contents: list[str] = []


def _dispatch_tool(
    name: str, tool_input: dict[str, Any], diff: NormalizedDiff, metadata: dict[str, Any]
) -> Any:
    if name == "lookup_package_registry":
        return tools.lookup_package_registry(**tool_input)
    if name == "fetch_referenced_file":
        content = tools.fetch_referenced_file(
            path=tool_input["path"], ref=tool_input["ref"], repo_path=diff.repo_path
        )
        # Mismo dato no confiable que el diff inicial, solo que llega por una
        # tool en vez de en el prompt original -- mismos delimitadores.
        return content, prompting.wrap_untrusted_content(content)
    if name == "check_file_reputation":
        return tools.check_file_reputation(
            path=tool_input["path"], ref=tool_input["ref"], repo_path=diff.repo_path
        )
    if name == "get_commit_history":
        fetch_commit_history = metadata.get("fetch_commit_history_callback")
        if fetch_commit_history is None:
            return {"error": "get_commit_history no disponible: sin adaptador inyectado"}
        tool = tools.make_get_commit_history_tool(fetch_commit_history)
        return tool(tool_input["author_login"], tool_input["repo"])
    return {"error": f"tool desconocida: {name}"}


def _build_tool_executor(
    diff: NormalizedDiff, metadata: dict[str, Any], counter: _ToolCallCounter
) -> ToolExecutor:
    def executor(name: str, tool_input: dict[str, Any]) -> Any:
        counter.count += 1
        if name == "fetch_referenced_file":
            # Cuenta el INTENTO de comprobar el contenido, no si la lectura
            # tuvo éxito -- si el LLM llamó a la tool y el fichero/ref no
            # existía (git show fallando), sigue siendo una comprobación real
            # hecha por su cuenta, no "nunca lo comprobó".
            counter.fetch_referenced_file_calls += 1
        try:
            if name == "fetch_referenced_file":
                raw_content, wrapped_content = _dispatch_tool(name, tool_input, diff, metadata)
                counter.fetched_contents.append(raw_content)
                return wrapped_content
            return _dispatch_tool(name, tool_input, diff, metadata)
        except Exception as exc:  # noqa: BLE001 - un tool_call con argumentos
            # mal formados (o cualquier fallo interno de una tool) no debe
            # tirar abajo toda la conversación con el LLM; se le devuelve el
            # error como resultado de la tool, igual que haría un fallo de red.
            return {"error": f"fallo ejecutando la tool {name!r}: {exc!r}"}

    return executor


def _diff_summary(diff: NormalizedDiff) -> str:
    return "\n".join(f"{fc.path}: {fc.diff_hunk[:200]}" for fc in diff.files)


def _chunk_rag_query(chunk: chunking.Chunk) -> str:
    return "\n".join(p.content[:200] for p in chunk.pieces)


class _DummyCostController:
    def budget_remaining(self, repo: str) -> float:
        return float("inf")

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def get_cached(self, diff_hash: str) -> SemanticOutput | None:
        return None

    def store_cached(self, diff_hash: str, output: SemanticOutput) -> None:
        pass

    def record_usage(self, repo: str, tokens: int) -> None:
        pass


@dataclass
class _CallResult:
    """Una llamada individual al LLM (un chunk del map, o la síntesis del
    reduce), con lo necesario para poder re-muestrearla (`_resample_winner`)
    y para escanear su texto en busca de inyección de prompt."""

    label: str  # "paquete (a.py, b.py)" / "síntesis global" -- solo para logs/depuración
    paths: list[str]  # ficheros de origen de este chunk (vacío para la síntesis global)
    system_prompt: str
    user_prompt: str
    output: SemanticOutput
    counter: _ToolCallCounter


@dataclass
class _Outcome:
    """Resultado uniforme de un análisis, venga de la única llamada
    (`_analyze_single`) o del map-reduce por chunks (`_analyze_chunked`) --
    `analyze()` aplica los suelos mecánicos/caché/coste sobre esto sin saber
    cuál de los dos caminos se tomó."""

    output: SemanticOutput
    tool_calls_made: int
    fetch_referenced_file_calls: int
    scanned_text: str
    has_unverified_marker: bool
    n_llm_calls: int
    prompt_tokens_total: int


@register_layer
class SemanticLayer(AnalysisLayer):
    name = "semantic"

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        cost_control: CostControllerLike | None = None,
        max_diff_tokens: int = 6000,
        project_type: str = "desconocido",
        languages: str = "desconocido",
        recent_activity_summary: str = "sin datos",
        rag_index_path: str = DEFAULT_INDEX_PATH,
        client_init_error: str | None = None,
        repo_graph_context: list[dict[str, Any]] | None = None,
    ) -> None:
        self._llm_client = llm_client
        # Motivo real por el que quien llama no pudo construir `llm_client`
        # (p. ej. `build_llm_client()` lanzó por un proveedor/clave mal
        # configurados) -- si se pasa, sustituye a _NO_LLM_CONFIG_SKIP_REASON
        # en el resultado. Sin esto, cualquier fallo de configuración real
        # (no solo "no hay clave") queda indistinguible de "no hay clave".
        self._client_init_error = client_init_error
        self._cost_control: CostControllerLike = (
            cost_control if cost_control is not None else _DummyCostController()  # type: ignore[assignment]
        )
        self._max_diff_tokens = max_diff_tokens
        self._project_type = project_type
        self._languages = languages
        self._recent_activity_summary = recent_activity_summary
        self._repo_graph_context = repo_graph_context
        self._rag_index_path = rag_index_path

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        if self._llm_client is None:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=(
                    f"Capa semántica omitida: no se pudo construir el cliente LLM "
                    f"({self._client_init_error})"
                    if self._client_init_error
                    else _NO_LLM_CONFIG_SKIP_REASON
                ),
            )

        repo = str(metadata.get("repo", ""))

        if self._cost_control is not None and self._cost_control.budget_remaining(repo) <= 0:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=_NO_BUDGET_SKIP_REASON,
            )

        diff_hash = compute_diff_hash(diff)
        cached = self._cost_control.get_cached(diff_hash) if self._cost_control else None
        if cached is not None:
            return self._to_layer_result(cached, tool_calls_made=0)

        static_findings_paths: set[str] = set(metadata.get("static_findings_paths", set()))
        org_id_raw = metadata.get("org_id")
        org_id = org_id_raw if isinstance(org_id_raw, str) else None
        dependency_findings = tools.gather_dependency_findings(diff)
        fits = prompting.diff_fits_budget(
            diff, self._cost_control.estimate_tokens, self._max_diff_tokens
        )

        try:
            if fits:
                outcome = self._analyze_single(
                    diff, metadata, static_findings_paths, org_id, dependency_findings
                )
            else:
                outcome = self._analyze_chunked(diff, metadata, org_id, dependency_findings)
        except SemanticParsingError as exc:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - frontera de aislamiento entre capas
            # Antes esto se reportaba con _NO_LLM_CONFIG_SKIP_REASON, el mismo
            # mensaje que "no hay clave de API configurada" -- indistinguible
            # de un error real de la llamada (límite de tokens superado, rate
            # limit, timeout de red...). Bug real, reproducido: un caso con un
            # fichero de 3.7 MB en el diff hacía que Gemini devolviera 400
            # INVALID_ARGUMENT (input token count excede el máximo permitido)
            # y el resultado decía "sin configuración de proveedor LLM",
            # llevando a pensar que faltaba una env var cuando la API sí
            # respondía, solo que con un error real. Con el análisis por
            # chunks (`_analyze_chunked`), cada llamada individual manda muy
            # por debajo de `max_diff_tokens` (muy por debajo del límite real
            # de cualquier proveedor), así que este caso concreto debería ser
            # ya residual -- se mantiene esta rama como red de seguridad para
            # cualquier otro fallo real de la API (rate limit, timeout...).
            logger.info("Capa semántica omitida por error de la API del proveedor LLM: %s", exc)
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=f"Capa semántica omitida por error de la API del proveedor LLM: {exc}",
            )

        output = _apply_prompt_injection_floor(outcome.output, outcome.scanned_text)
        output = _apply_unverified_content_floor(
            output, outcome.has_unverified_marker, outcome.fetch_referenced_file_calls
        )
        self._cost_control.store_cached(diff_hash, output)
        # Nota: esto estima el coste de todas las llamadas hechas (1 en el
        # camino de una sola llamada, o más si hubo auto-consistencia; N
        # paquetes + 1 síntesis + resampling del ganador en el camino por
        # chunks), pero no puede contabilizar las idas y vueltas de
        # tool-calls ni los tokens de salida del modelo, porque
        # LLMClient.complete_structured no expone el consumo real de la
        # conversación (§7.3/§8 no lo definen). Subestima el uso real cuando
        # hay tool calls; documentado para quien integre cost_control.py de
        # verdad.
        self._cost_control.record_usage(repo, outcome.prompt_tokens_total)
        return self._to_layer_result(output, tool_calls_made=outcome.tool_calls_made)

    def _analyze_single(
        self,
        diff: NormalizedDiff,
        metadata: dict[str, Any],
        static_findings_paths: set[str],
        org_id: str | None,
        dependency_findings: list[dict[str, Any]],
    ) -> _Outcome:
        """Camino sin cambios respecto al análisis de una sola llamada: el
        diff completo cabe en `max_diff_tokens` (con el truncado heurístico
        de `build_user_prompt` como mucho, sin necesidad de chunking)."""
        rag_context = retrieve_relevant_context(
            _diff_summary(diff), index_path=self._rag_index_path, org_id=org_id
        )
        system_prompt = prompting.build_system_prompt(
            self._project_type,
            self._languages,
            self._recent_activity_summary,
            rag_context,
            dependency_findings=dependency_findings,
            repo_graph_context=self._repo_graph_context,
        )
        user_prompt = prompting.build_user_prompt(
            diff, static_findings_paths, self._cost_control.estimate_tokens, self._max_diff_tokens
        )
        output, counter = self._call_llm_once(system_prompt, user_prompt, diff, metadata)
        n_calls = 1
        prompt_tokens = self._cost_control.estimate_tokens(
            system_prompt
        ) + self._cost_control.estimate_tokens(user_prompt)

        if _is_borderline_score(output.risk_score):
            for _ in range(_MAX_RESAMPLES):
                try:
                    extra_output, extra_counter = self._call_llm_once(
                        system_prompt, user_prompt, diff, metadata
                    )
                except SemanticParsingError:
                    # Una muestra que no parsea no invalida las demás -- ya
                    # tenemos al menos la primera, válida.
                    continue
                n_calls += 1
                prompt_tokens += self._cost_control.estimate_tokens(
                    system_prompt
                ) + self._cost_control.estimate_tokens(user_prompt)
                if extra_output.risk_score > output.risk_score:
                    output, counter = extra_output, extra_counter

        scanned_text = user_prompt
        if counter.fetched_contents:
            scanned_text = "\n".join([user_prompt, *counter.fetched_contents])

        return _Outcome(
            output=output,
            tool_calls_made=counter.count,
            fetch_referenced_file_calls=counter.fetch_referenced_file_calls,
            scanned_text=scanned_text,
            has_unverified_marker=prompting.UNVERIFIED_CONTENT_MARKER in user_prompt,
            n_llm_calls=n_calls,
            prompt_tokens_total=prompt_tokens,
        )

    def _run_map_chunk(
        self,
        chunk: chunking.Chunk,
        diff: NormalizedDiff,
        metadata: dict[str, Any],
        org_id: str | None,
        dependency_findings: list[dict[str, Any]],
    ) -> _CallResult | None:
        """Una llamada del "map": un paquete de ficheros que ya cabe entero
        por construcción (`chunking.pack_pieces`), analizado exactamente
        igual que un análisis normal (mismo esquema de salida, mismas
        tools). `None` si esta llamada concreta falla -- ese paquete queda
        fuera del resto del análisis, reportado como no verificado en la
        síntesis (`_analyze_chunked`), en vez de tumbar todo el análisis."""
        paths = sorted(chunk.source_paths)
        rag_context = retrieve_relevant_context(
            _chunk_rag_query(chunk), index_path=self._rag_index_path, org_id=org_id
        )
        system_prompt = prompting.build_system_prompt(
            self._project_type,
            self._languages,
            self._recent_activity_summary,
            rag_context,
            dependency_findings=dependency_findings,
            repo_graph_context=self._repo_graph_context,
        )
        user_prompt = prompting.build_chunk_user_prompt(diff, chunk.render())
        try:
            output, counter = self._call_llm_once(system_prompt, user_prompt, diff, metadata)
        except Exception as exc:  # noqa: BLE001 - un paquete fallido no debe tumbar el resto
            logger.info(
                "Paquete semántico omitido por error de la API del proveedor LLM (%s): %s",
                paths,
                exc,
            )
            return None
        return _CallResult(
            label=f"paquete ({', '.join(paths)})",
            paths=paths,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output=output,
            counter=counter,
        )

    def _resample_if_borderline(
        self, call: _CallResult, diff: NormalizedDiff, metadata: dict[str, Any]
    ) -> tuple[_CallResult, int, int]:
        """Auto-consistencia genérica: re-ejecuta EXACTAMENTE el mismo
        system/user prompt de `call` hasta `_MAX_RESAMPLES` veces si su
        risk_score cae cerca de un umbral, y se queda con la muestra de
        mayor risk_score. Aplica tanto a la única llamada del camino simple
        como al "ganador" (chunk o síntesis) del camino por chunks -- mismo
        criterio en los dos casos. Devuelve `(call_final, n_calls_extra,
        tokens_extra)`."""
        if not _is_borderline_score(call.output.risk_score):
            return call, 0, 0
        n_extra = 0
        tokens_extra = 0
        best = call
        for _ in range(_MAX_RESAMPLES):
            try:
                extra_output, extra_counter = self._call_llm_once(
                    call.system_prompt, call.user_prompt, diff, metadata
                )
            except SemanticParsingError:
                continue
            n_extra += 1
            tokens_extra += self._cost_control.estimate_tokens(
                call.system_prompt
            ) + self._cost_control.estimate_tokens(call.user_prompt)
            if extra_output.risk_score > best.output.risk_score:
                best = _CallResult(
                    label=call.label,
                    paths=call.paths,
                    system_prompt=call.system_prompt,
                    user_prompt=call.user_prompt,
                    output=extra_output,
                    counter=extra_counter,
                )
        return best, n_extra, tokens_extra

    def _analyze_chunked(
        self,
        diff: NormalizedDiff,
        metadata: dict[str, Any],
        org_id: str | None,
        dependency_findings: list[dict[str, Any]],
    ) -> _Outcome:
        """El diff no cabe en `max_diff_tokens` ni truncado. Map: cada
        paquete de ficheros (`chunking.pack_pieces`, agrupados priorizando
        ficheros que se referencian entre sí) se analiza en su propia
        llamada, en paralelo. Reduce: una llamada final de síntesis recibe
        SOLO los resultados compactos de cada paquete (no los diffs otra
        vez) y decide si hay riesgo transversal entre ficheros de paquetes
        distintos. El risk_score final es el máximo entre la síntesis y
        cualquier paquete individual -- la síntesis puede escalar (ve el
        conjunto completo) pero nunca silenciar lo que un paquete ya marcó
        alto (mismo patrón de "suelo mecánico" que `_apply_*_floor`)."""
        pieces = chunking.build_pieces(
            diff.files, self._cost_control.estimate_tokens, self._max_diff_tokens
        )
        # Imports explícitos + literales notables compartidos (URLs/IPs/
        # blobs -- correlación tipo IOC entre ficheros que no se importan
        # entre sí, ver comentario junto a `build_symbol_reference_graph`
        # sobre por qué esto y no similitud de embeddings).
        reference_graph = chunking.merge_reference_graphs(
            chunking.build_reference_graph(diff.files),
            chunking.build_symbol_reference_graph(diff.files),
        )
        chunks, overflow_pieces = chunking.pack_pieces(
            pieces, reference_graph, self._max_diff_tokens
        )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(_CHUNK_WORKERS, len(chunks)))
        ) as pool:
            map_results = list(
                pool.map(
                    lambda c: self._run_map_chunk(c, diff, metadata, org_id, dependency_findings),
                    chunks,
                )
            )

        calls: list[_CallResult] = [r for r in map_results if r is not None]
        failed_paths = sorted(
            {
                p
                for c, r in zip(chunks, map_results, strict=True)
                if r is None
                for p in c.source_paths
            }
        )
        overflow_paths = sorted({p.source_path for p in overflow_pieces}) + failed_paths

        n_llm_calls = len(chunks)  # se intentó una llamada por chunk, aunque fallara
        prompt_tokens_total = sum(
            self._cost_control.estimate_tokens(c.system_prompt)
            + self._cost_control.estimate_tokens(c.user_prompt)
            for c in calls
        )

        chunk_summaries = [(c.paths, c.output) for c in calls]

        reduce_rag = retrieve_relevant_context(
            _diff_summary(diff), index_path=self._rag_index_path, org_id=org_id
        )
        reduce_system_prompt = prompting.build_reduce_system_prompt(
            self._project_type,
            self._languages,
            self._recent_activity_summary,
            reduce_rag,
            dependency_findings=dependency_findings,
            repo_graph_context=self._repo_graph_context,
        )
        reduce_user_prompt = prompting.build_reduce_user_prompt(
            diff, chunk_summaries, overflow_paths
        )
        reduce_output, reduce_counter = self._call_llm_once(
            reduce_system_prompt, reduce_user_prompt, diff, metadata
        )
        reduce_call = _CallResult(
            label="síntesis global",
            paths=[],
            system_prompt=reduce_system_prompt,
            user_prompt=reduce_user_prompt,
            output=reduce_output,
            counter=reduce_counter,
        )
        n_llm_calls += 1
        prompt_tokens_total += self._cost_control.estimate_tokens(
            reduce_system_prompt
        ) + self._cost_control.estimate_tokens(reduce_user_prompt)

        candidates = [*calls, reduce_call]
        winner = max(candidates, key=lambda c: c.output.risk_score)
        winner, n_extra, tokens_extra = self._resample_if_borderline(winner, diff, metadata)
        n_llm_calls += n_extra
        prompt_tokens_total += tokens_extra

        if winner is reduce_call:
            combined_output = reduce_output
        else:
            # Un paquete individual ganó a la síntesis: se mantiene su
            # veredicto (categoría/naturaleza/confianza propias), pero se
            # añade la lectura de la síntesis como nota -- nunca se pierde
            # ninguna de las dos perspectivas.
            combined_output = winner.output.model_copy(
                update={
                    "justification": (
                        f"{winner.output.justification} "
                        f"[Nota de síntesis global: {reduce_output.justification}]"
                    )
                }
            )

        scanned_texts = [c.user_prompt for c in candidates]
        for c in candidates:
            scanned_texts.extend(c.counter.fetched_contents)

        return _Outcome(
            output=combined_output,
            tool_calls_made=sum(c.counter.count for c in candidates),
            fetch_referenced_file_calls=sum(
                c.counter.fetch_referenced_file_calls for c in candidates
            ),
            scanned_text="\n".join(scanned_texts),
            has_unverified_marker=bool(overflow_paths),
            n_llm_calls=n_llm_calls,
            prompt_tokens_total=prompt_tokens_total,
        )

    def _call_llm_once(
        self,
        system_prompt: str,
        user_prompt: str,
        diff: NormalizedDiff,
        metadata: dict[str, Any],
    ) -> tuple[SemanticOutput, _ToolCallCounter]:
        assert self._llm_client is not None
        counter = _ToolCallCounter()
        tool_executor = _build_tool_executor(diff, metadata, counter)
        output = self._llm_client.complete_structured(
            system_prompt,
            user_prompt,
            tools=tools.build_tool_schemas(),
            tool_executor=tool_executor,
            max_tool_calls=_MAX_TOOL_CALLS,
        )
        return output, counter

    def _to_layer_result(self, output: SemanticOutput, tool_calls_made: int) -> LayerResult:
        finding = Finding(
            file_path="diferencial_pr",
            rule_id="semantic-llm-analysis",
            message=output.justification,
            severity="error" if output.risk_score >= 70 else "warning",
            threat_nature=output.threat_nature,
        )
        return LayerResult(
            layer_name=self.name,
            risk_score=output.risk_score,
            justification=output.justification,
            findings=[finding],
            category=output.category,
            confidence=output.confidence,
            threat_nature=output.threat_nature,
            tool_calls_made=tool_calls_made,
        )
