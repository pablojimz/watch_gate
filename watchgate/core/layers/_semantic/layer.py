"""SemanticLayer — orquesta prompting/tools/client/RAG (§7.5).

`cost_control` se recibe como un `CostControllerLike` (Protocol estructural):
esta capa no importa `watchgate.core.cost_control` directamente, así que es
testeable con un fake y se integra con la implementación real de esa pieza
(§8) sin cambiar una línea aquí — solo pasando la instancia real al
constructor.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Protocol

from watchgate.core.aggregator import DEFAULT_THRESHOLDS
from watchgate.core.layers._semantic import prompting, tools
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
    output: SemanticOutput, user_prompt: str, fetch_referenced_file_calls: int
) -> SemanticOutput:
    if (
        prompting.UNVERIFIED_CONTENT_MARKER not in user_prompt
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
# que intenta manipular al LLM -- "ignora las instrucciones anteriores",
# falsos mensajes de sistema, JSON de respuesta falsificado incrustado en un
# comentario -- eso es evidencia de intención maliciosa por sí sola, la
# haya seguido el modelo o no. Un PR legítimo nunca necesita decirle a un
# revisor (humano o IA) que ignore sus instrucciones; el intento en sí es el
# hallazgo. 100, no un umbral calculado: no queda margen de duda razonable
# aquí como sí lo hay con "no se pudo revisar" -- no es una escala de
# incertidumbre, es una prueba directa.
_PROMPT_INJECTION_FLOOR_SCORE = 100
_NO_LLM_CONFIG_SKIP_REASON = (
    "Capa semántica omitida (requiere clave de API o configuración de proveedor LLM en el entorno)"
)


def _apply_prompt_injection_floor(output: SemanticOutput, scanned_text: str) -> SemanticOutput:
    findings = find_prompt_injection_attempts(scanned_text)
    if not findings or output.risk_score >= _PROMPT_INJECTION_FLOOR_SCORE:
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
    ) -> None:
        self._llm_client = llm_client
        self._cost_control: CostControllerLike = (
            cost_control if cost_control is not None else _DummyCostController()  # type: ignore[assignment]
        )
        self._max_diff_tokens = max_diff_tokens
        self._project_type = project_type
        self._languages = languages
        self._recent_activity_summary = recent_activity_summary
        self._rag_index_path = rag_index_path

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        if self._llm_client is None:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=_NO_LLM_CONFIG_SKIP_REASON,
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
        rag_context = retrieve_relevant_context(
            _diff_summary(diff),
            index_path=self._rag_index_path,
            org_id=org_id_raw if isinstance(org_id_raw, str) else None,
        )
        dependency_findings = tools.gather_dependency_findings(diff)

        system_prompt = prompting.build_system_prompt(
            self._project_type,
            self._languages,
            self._recent_activity_summary,
            rag_context,
            dependency_findings=dependency_findings,
        )
        user_prompt = prompting.build_user_prompt(
            diff, static_findings_paths, self._cost_control.estimate_tokens, self._max_diff_tokens
        )

        try:
            output, counter = self._call_llm_once(system_prompt, user_prompt, diff, metadata)
        except SemanticParsingError as exc:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("Capa semántica omitida por cliente LLM no disponible: %s", exc)
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=_NO_LLM_CONFIG_SKIP_REASON,
            )

        n_calls = 1
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
                if extra_output.risk_score > output.risk_score:
                    output, counter = extra_output, extra_counter

        scanned_text = user_prompt
        if counter.fetched_contents:
            scanned_text = "\n".join([user_prompt, *counter.fetched_contents])
        output = _apply_prompt_injection_floor(output, scanned_text)
        output = _apply_unverified_content_floor(
            output, user_prompt, counter.fetch_referenced_file_calls
        )
        self._cost_control.store_cached(diff_hash, output)
        # Nota: esto estima el coste de la petición inicial (system + user
        # prompt) multiplicado por el número real de llamadas hechas (1, o
        # más si hubo auto-consistencia), pero no puede contabilizar las idas
        # y vueltas de tool-calls ni los tokens de salida del modelo, porque
        # LLMClient.complete_structured no expone el consumo real de la
        # conversación (§7.3/§8 no lo definen). Subestima el uso real cuando
        # hay tool calls; documentado para quien integre cost_control.py de
        # verdad.
        estimated_tokens = n_calls * (
            self._cost_control.estimate_tokens(system_prompt)
            + self._cost_control.estimate_tokens(user_prompt)
        )
        self._cost_control.record_usage(repo, estimated_tokens)
        return self._to_layer_result(output, tool_calls_made=counter.count)

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
