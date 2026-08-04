"""Orquestador de ejecución de capas (spec §9, A.1).

Regla explícita de la spec: este módulo no debe contener ningún `if` que
decida *qué* capa ejecutar, más allá del filtro por `weight > 0` leído de
config. Cualquier lógica condicional adicional (p. ej. los cortocircuitos de
A.3.4) vive en `shortcircuit.py` y se invoca *antes* de `run_analysis`.
"""

from __future__ import annotations

import concurrent.futures
from typing import Protocol, runtime_checkable

from watchgate.core.aggregator import aggregate
from watchgate.core.layers.base import LAYER_REGISTRY, AnalysisLayer, safe_analyze
from watchgate.core.models import AggregatedResult, NormalizedDiff


@runtime_checkable
class WatchGateConfig(Protocol):
    """Contrato mínimo que `run_analysis` necesita de la configuración.

    Se define como Protocol (duck typing) en vez de importar la clase real
    de `config.py` para no acoplar el orquestador al módulo de config
    concreto; cualquier objeto con estos dos atributos sirve.
    """

    weights: dict[str, float]
    thresholds: dict[str, int]


def run_analysis(
    diff: NormalizedDiff, metadata: dict[str, object], config: WatchGateConfig
) -> AggregatedResult:
    """Instancia las capas activas (peso > 0 y registradas), las ejecuta en
    paralelo con `safe_analyze` y agrega el resultado final."""
    active_layers: list[AnalysisLayer] = [
        LAYER_REGISTRY[name]()
        for name, weight in config.weights.items()
        if weight > 0 and name in LAYER_REGISTRY
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(active_layers) or 1) as pool:
        futures = {
            pool.submit(safe_analyze, layer, diff, metadata): layer.name
            for layer in active_layers
        }
        results = {futures[f]: f.result() for f in concurrent.futures.as_completed(futures)}

    return aggregate(
        results,
        config.weights,
        diff,
        pr_id=str(metadata.get("pr_id", "")),
        repo=str(metadata.get("repo", "")),
        thresholds=getattr(config, "thresholds", None),
    )
