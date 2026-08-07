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


def _semaforo(score: int, thresholds: dict[str, int]) -> Semaforo:
    if score >= thresholds["red"]:
        return Semaforo.ROJO
    if score >= thresholds["yellow"]:
        return Semaforo.AMARILLO
    return Semaforo.VERDE


def _apply_malicious_and_uncertain_policy(
    score: int,
    results: dict[str, LayerResult],
    diff: NormalizedDiff | None,
    thresholds: dict[str, int],
) -> tuple[int, Semaforo]:
    has_high_confidence_malicious = False
    has_medium_confidence_malicious = False

    for layer_res in results.values():
        if layer_res.skipped:
            continue
        if layer_res.threat_nature == ThreatNature.MALICIOUS:
            if layer_res.confidence == Confidence.ALTA or layer_res.risk_score >= thresholds["red"]:
                has_high_confidence_malicious = True
            elif layer_res.confidence == Confidence.MEDIA or layer_res.risk_score >= 50:
                has_medium_confidence_malicious = True

    if has_high_confidence_malicious:
        return 100, Semaforo.ROJO

    if has_medium_confidence_malicious:
        score = max(score, thresholds["red"])

    if diff and diff.files:
        from watchgate.core.layers._semantic.prompting import UNVERIFIED_CONTENT_MARKER

        uncertain_files_count = sum(
            1 for fc in diff.files if UNVERIFIED_CONTENT_MARKER in fc.diff_hunk
        )
        if uncertain_files_count / len(diff.files) > 0.5 and score < thresholds["yellow"]:
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
    score, semaforo = _apply_malicious_and_uncertain_policy(score, results, diff, thresholds)

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
        pr_id=pr_id,
        repo=repo,
        timestamp=datetime.now(UTC).isoformat(),
        threat_summary=threat_summary,
    )
