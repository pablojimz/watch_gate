"""Agregación ponderada de resultados de capas (spec §10, A.2)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from watchgate.core.models import (
    AggregatedResult,
    Confidence,
    LayerResult,
    NormalizedDiff,
    RiskCategory,
    Semaforo,
    ThreatNature,
)

# Umbrales por defecto (score >= red -> ROJO, score >= yellow -> AMARILLO).
DEFAULT_THRESHOLDS: dict[str, int] = {"yellow": 40, "red": 70}

# Categorías graves donde una detección semántica de alta confianza no debe
# diluirse por debajo del umbral rojo solo porque otra capa (típicamente
# reputación) no ve nada raro -- el caso simétrico al que ya resuelve
# shortcircuit.py para "parcial alto, semántica baja": aquí es "semántica muy
# alta y de confianza, resto de capas bajo".
_SEVERE_CATEGORIES = frozenset(
    {
        RiskCategory.BACKDOOR,
        RiskCategory.EXFILTRACION,
        RiskCategory.ESCALADA_PRIVILEGIOS,
        RiskCategory.OFUSCACION,
    }
)
# Calibrado contra un caso real: una campaña de compromiso de paquetes npm
# (script "bun.sh/install | bash" inyectado) daba semantic=90,
# confidence=alta, categoría backdoor -- pero la cuenta comprometida no tenía
# ninguna señal de reputación sospechosa (ese es justo el objetivo del
# ataque), así que el combinado se quedaba en 65, por debajo del umbral rojo
# por muy poco. Verificado contra la suite de validación real (tests/cases/).
#
# OFUSCACION se añadió tras encontrar el mismo problema con la detección
# mecánica de inyección de prompt (`_apply_prompt_injection_floor` en
# `_semantic/layer.py`): fuerza semantic=100/confidence=alta/categoría
# ofuscación de forma determinista (el intento en sí es la prueba, sin
# margen de duda), pero al no estar antes en este set, el peso nominal de
# `semantic` (0.40 desde que hay 5 capas reales) dejaba el combinado en 51
# -- por debajo del umbral rojo -- porque static/dependencies/vulnerabilities
# no tienen ninguna señal que ver en un ataque que vive en un comentario o
# docstring, no en el código ejecutable. Reproducido en vivo con
# `tests/cases/prompt_injection_fake_approval` y
# `tests/cases/prompt_injection_hides_real_payload`.
_SEMANTIC_FLOOR_MIN_SCORE = 85


def _apply_high_confidence_semantic_floor(
    score: int, results: dict[str, LayerResult], thresholds: dict[str, int]
) -> int:
    """Si la capa semántica, por sí sola, es de alta confianza y categoría
    grave con un score muy alto, el score combinado nunca baja del umbral
    rojo -- una reputación limpia (o cualquier otra capa baja) es una señal
    real, pero no debe poder anular una detección de contenido tan clara."""
    semantic = results.get("semantic")
    if (
        semantic is None
        or semantic.skipped
        or semantic.confidence != Confidence.ALTA
        or semantic.category not in _SEVERE_CATEGORIES
        or semantic.risk_score < _SEMANTIC_FLOOR_MIN_SCORE
    ):
        return score
    return max(score, thresholds["red"])


def weighted_average(
    results: dict[str, LayerResult],
    weights: dict[str, float],
    layer_names: Iterable[str] | None = None,
) -> float:
    """Media ponderada de `risk_score`, excluyendo capas `skipped` o sin
    peso asignado (`weights.get(k, 0) <= 0`).

    Si se da `layer_names`, restringe el cálculo a esas claves — lo usa
    `shortcircuit.py` (§11) para el score parcial `static+deps+reputation`
    sin incluir `semantic`, reutilizando exactamente la misma fórmula que
    `aggregate()` usa para el score final.

    Protegido contra división por cero: si no queda ninguna capa activa
    tras el filtro, el denominador usa un epsilon.
    """
    candidates = (
        results if layer_names is None else {k: v for k, v in results.items() if k in layer_names}
    )
    active = {k: v for k, v in candidates.items() if not v.skipped and weights.get(k, 0) > 0}
    total_weight = sum(weights[k] for k in active) or 1e-9
    return sum(weights[k] * active[k].risk_score for k in active) / total_weight


def compute_effective_weights(
    results: dict[str, LayerResult], weights: dict[str, float]
) -> dict[str, float]:
    """Calcula los pesos re-normalizados al 100% (suma = 1.0) para las capas
    activas (no omitidas con peso nominal > 0). Las capas omitidas o con
    peso nominal <= 0 reciben un peso efectivo de 0.0.
    """
    active = {k: v for k, v in results.items() if not v.skipped and weights.get(k, 0) > 0}
    total_weight = sum(weights[k] for k in active)
    if total_weight <= 0:
        return {k: 0.0 for k in weights}

    return {k: round(weights[k] / total_weight, 4) if k in active else 0.0 for k in weights}


def _semaforo(score: int, thresholds: dict[str, int]) -> Semaforo:
    if score >= thresholds["red"]:
        return Semaforo.ROJO
    if score >= thresholds["yellow"]:
        return Semaforo.AMARILLO
    return Semaforo.VERDE


def _apply_malicious_and_uncertain_policy(
    score: int,
    results: dict[str, LayerResult],
    thresholds: dict[str, int],
) -> tuple[int, Semaforo]:
    # Exigir `confidence` explícita (no "o risk_score >= umbral") -- ese
    # `or` trataba un risk_score alto como si fuera lo mismo que alta
    # confianza, pero no lo es. Reproducido en vivo fijando "left-pad":
    # "git+https://.../left-pad.git#v1.3.1-hotfix" en package.json (score
    # ~10/100 real, ROJO forzado por el heurístico mecánico solo).
    #
    # Restringido a la capa `semantic` EXPLÍCITAMENTE, no "cualquier capa
    # con confidence == ALTA/MEDIA" -- bug real, reproducido en vivo dos
    # veces en la misma sesión: este comentario decía "deps_layer.py nunca
    # rellena confidence (siempre None)" porque así era cuando se escribió
    # el fix de arriba, pero tanto `deps_layer.py` como `static_layer.py`
    # ganaron después su propia regla mecánica "si mi risk_score llega a
    # 70, confidence = ALTA" (para mostrar algo razonable en el dashboard),
    # sin que nadie revisara si ESTA función seguía asumiendo lo contrario.
    # Resultado: el mismo veto absoluto de un heurístico mecánico sin
    # corroboración que el fix de "left-pad" pretendía cerrar volvió a
    # colarse por la puerta de al lado -- typosquatting por distancia de
    # Levenshtein en nombres de 2-4 caracteres ('gopd'~'got', 'c8'~'d3') y
    # el regex `exec_dynamic` cazando `regex.exec(...)` en JS/TS forzaban
    # cualquier PR a 70/ROJO aunque semantic y el resto dijeran "esto es
    # benigno". La `confidence` de `semantic` sí refleja razonamiento real
    # (la rellena un LLM que ha visto el diff completo); la de
    # `deps`/`static`/`vulnerabilities` es solo el propio `risk_score`
    # reetiquetado -- no aporta corroboración independiente, así que no
    # puede tener este veto.
    semantic_for_escalation = results.get("semantic")
    has_high_confidence_malicious = False
    has_medium_confidence_malicious = False
    if (
        semantic_for_escalation is not None
        and not semantic_for_escalation.skipped
        and semantic_for_escalation.threat_nature == ThreatNature.MALICIOUS
    ):
        if semantic_for_escalation.confidence == Confidence.ALTA:
            has_high_confidence_malicious = True
        elif semantic_for_escalation.confidence == Confidence.MEDIA:
            has_medium_confidence_malicious = True

    if has_high_confidence_malicious or has_medium_confidence_malicious:
        score = max(score, thresholds["red"])

    # Mismo criterio que arriba (solo `semantic`, ver el comentario largo):
    # si detecta un hallazgo de alta confianza con puntuación elevada
    # (>= red), el resultado global no debe diluirse por debajo del umbral
    # amarillo.
    if (
        semantic_for_escalation is not None
        and not semantic_for_escalation.skipped
        and semantic_for_escalation.confidence == Confidence.ALTA
        and semantic_for_escalation.risk_score >= thresholds["red"]
        and score < thresholds["yellow"]
    ):
        score = thresholds["yellow"]

    # Bug real encontrado regenerando el informe de validación (caso
    # `malreal_pypi_malicious_intent_mirrorbot_10`): esta escalada
    # comprobaba `UNVERIFIED_CONTENT_MARKER in fc.diff_hunk` sobre el
    # `NormalizedDiff` original -- pero ese marcador solo se inserta en el
    # STRING del prompt que construye `prompting.py` para el LLM
    # (`_render_truncated_file_change`), nunca se escribe de vuelta en
    # `file_change.diff_hunk`. La condición era código muerto: nunca podía
    # cumplirse, así que esta "red de seguridad" jamás disparaba en
    # producción (sin test de regresión que lo cubriera tampoco). Caso real
    # reproducido: contenido truncado sin verificar + `fetch_referenced_file`
    # nunca llamado -- `_apply_unverified_content_floor` (`_semantic/layer.py`)
    # sí flota el risk_score de la propia capa semántica a >=60 y marca
    # `threat_nature=UNCERTAIN`, pero con los pesos por defecto (semantic=0.40)
    # y las demás capas activas puntuando 0 (nada que reportar, no `skipped`),
    # el combinado se queda por debajo de `thresholds["yellow"]` de todas
    # formas -- el PR se marca verde pese a que la propia capa semántica ya
    # señaló "no pude comprobar esto".
    #
    # Arreglado consultando directamente el `threat_nature` que ya calculó la
    # capa semántica (no reconstruyendo la misma señal de forma redundante e
    # inconsistente desde el diff): si marcó incertidumbre real, el combinado
    # nunca se queda por debajo de AMARILLO.
    #
    # OJO, segundo bug encontrado regenerando el informe tras el primer
    # arreglo (caso `benign_refactor`, un renombrado cosmético sin riesgo
    # real): `threat_nature` es un campo que el LLM rellena libremente en su
    # propia salida estructurada (`SemanticOutput.threat_nature`, ver
    # `client.py`/prompting.py) -- NO es exclusivo de
    # `_apply_unverified_content_floor` (`_semantic/layer.py`). El modelo
    # puede devolver `threat_nature="incertidumbre"` con un `risk_score`
    # bajísimo (p. ej. 5) solo por prudencia genérica, sin que exista
    # contenido truncado sin verificar de por medio. Comprobar solo
    # `threat_nature == UNCERTAIN` disparaba el suelo para CUALQUIER
    # incertidumbre autoreportada por el modelo, por trivial que fuera --
    # forzando amarillo en diffs limpios de verdad. Se exige además que el
    # propio risk_score de la capa ya haya alcanzado por sí solo el umbral
    # amarillo: eso es justo lo que distingue "el suelo local de
    # `_apply_unverified_content_floor` disparó de verdad" (fuerza el score
    # a >=60) de "el modelo eligió la etiqueta 'incertidumbre' con un score
    # que ya refleja que no le preocupa".
    semantic_result = results.get("semantic")
    if (
        semantic_result is not None
        and not semantic_result.skipped
        and semantic_result.threat_nature == ThreatNature.UNCERTAIN
        and semantic_result.risk_score >= thresholds["yellow"]
        and score < thresholds["yellow"]
    ):
        score = thresholds["yellow"]

    return score, _semaforo(score, thresholds)


def aggregate(
    results: dict[str, LayerResult],
    weights: dict[str, float],
    diff: NormalizedDiff | None,
    pr_id: str,
    repo: str,
    thresholds: dict[str, int] | None = None,
) -> AggregatedResult:
    """Combina los LayerResult de todas las capas ejecutadas en un único
    AggregatedResult, ponderando por `weights` y excluyendo las capas
    omitidas (`skipped=True`) o sin peso asignado.

    `diff` no se usa todavía en el cálculo del score (se recibe para
    mantener la firma exacta que invoca `orchestrator.py`, y por si en el
    futuro se necesita contexto por-fichero en la agregación).
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    score = round(weighted_average(results, weights))
    score = _apply_high_confidence_semantic_floor(score, results, thresholds)
    score, semaforo = _apply_malicious_and_uncertain_policy(score, results, thresholds)

    threat_summary = {
        ThreatNature.MALICIOUS.value: 0,
        ThreatNature.VULNERABILITY.value: 0,
        ThreatNature.UNCERTAIN.value: 0,
    }
    for layer_res in results.values():
        if layer_res.skipped:
            continue
        for f in layer_res.findings:
            t_val = f.threat_nature.value
            threat_summary[t_val] = threat_summary.get(t_val, 0) + 1

    return AggregatedResult(
        score=score,
        semaforo=semaforo,
        layer_results=results,
        weights_used=weights,
        effective_weights=compute_effective_weights(results, weights),
        pr_id=pr_id,
        repo=repo,
        timestamp=datetime.now(UTC).isoformat(),
        threat_summary=threat_summary,
    )
