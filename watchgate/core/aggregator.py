"""Agregación ponderada de resultados de capas (spec §10, A.2)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from watchgate.core.models import AggregatedResult, LayerResult, NormalizedDiff, Semaforo

# Umbrales por defecto (score >= red -> ROJO, score >= yellow -> AMARILLO).
DEFAULT_THRESHOLDS: dict[str, int] = {"yellow": 40, "red": 70}


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
    semaforo = _semaforo(score, thresholds)
    return AggregatedResult(
        score=score,
        semaforo=semaforo,
        layer_results=results,
        weights_used=weights,
        pr_id=pr_id,
        repo=repo,
        timestamp=datetime.now(UTC).isoformat(),
    )
