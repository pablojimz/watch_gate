"""Agregación ponderada de resultados de capas (spec §10, A.2)."""

from __future__ import annotations

from datetime import UTC, datetime

from watchgate.core.models import AggregatedResult, LayerResult, NormalizedDiff, Semaforo

# Umbrales por defecto (score >= red -> ROJO, score >= yellow -> AMARILLO).
DEFAULT_THRESHOLDS: dict[str, int] = {"yellow": 40, "red": 70}


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

    Si todas las capas activas están omitidas (score sin ninguna señal),
    el denominador se protege con un epsilon para no dividir por cero.

    `diff` no se usa todavía en el cálculo del score (se recibe para
    mantener la firma exacta que invoca `orchestrator.py`, y por si en el
    futuro se necesita contexto por-fichero en la agregación).
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    active = {k: v for k, v in results.items() if not v.skipped and weights.get(k, 0) > 0}
    total_weight = sum(weights[k] for k in active) or 1e-9
    score = round(sum(weights[k] * active[k].risk_score for k in active) / total_weight)
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
