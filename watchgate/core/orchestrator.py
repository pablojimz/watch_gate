"""Orquestador de ejecución de capas (spec §9, A.1).

Regla explícita de la spec: este módulo no debe contener ningún `if` que
decida *qué* capa ejecutar, más allá del filtro por `weight > 0` leído de
config. Cualquier lógica condicional adicional (p. ej. los cortocircuitos de
A.3.4) vive en `shortcircuit.py` y se invoca *antes* de `run_analysis`.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from watchgate.core.aggregator import aggregate
from watchgate.core.layers.base import LAYER_REGISTRY, AnalysisLayer, safe_analyze
from watchgate.core.models import AggregatedResult, LayerResult, NormalizedDiff

LayerFactory = Callable[[], AnalysisLayer]
ProgressCallback = Callable[[str, str], None]  # (layer_name, status: "start" | "done" | "fail")


@runtime_checkable
class WatchGateConfig(Protocol):
    """Contrato mínimo que `run_analysis` necesita de la configuración.

    Se define como Protocol (duck typing) en vez de importar la clase real
    de `config.py` para no acoplar el orquestador al módulo de config
    concreto; cualquier objeto con estos dos atributos sirve.
    """

    weights: dict[str, float]
    thresholds: dict[str, int]


def _build_and_analyze(
    name: str,
    factory: LayerFactory,
    diff: NormalizedDiff,
    metadata: dict[str, object],
    on_progress: ProgressCallback | None = None,
) -> LayerResult:
    """Construye la instancia de la capa Y la ejecuta, ambas dentro del
    mismo aislamiento por capa.

    Auditoría: antes solo `.analyze()` estaba protegido por `safe_analyze`
    -- la CONSTRUCCIÓN (`factory()`/`LAYER_REGISTRY[name]()`) corría fuera
    de cualquier try/except y fuera del ThreadPoolExecutor, así que una
    excepción ahí (p.ej. `VulnerabilitiesLayer.__init__` -> `OSVCache.
    __init__` hace I/O real de disco y puede fallar por permisos/disco
    lleno) tumbaba TODO `run_analysis`, perdiendo también los resultados
    de las demás capas que sí habían terminado bien -- confirmado en vivo.
    Se usa `name` (la clave de `config.weights`, no `layer.name`) para
    poder atribuir el fallo a la capa correcta incluso cuando la
    construcción en sí es lo que falló y nunca llegó a existir un objeto
    `layer` del que leer `.name`."""
    if on_progress:
        try:
            on_progress(name, "start")
        except Exception:  # noqa: BLE001
            pass
    try:
        layer = factory()
    except Exception as e:  # noqa: BLE001 -- misma frontera de aislamiento que safe_analyze
        res = LayerResult(
            layer_name=name,
            risk_score=0,
            justification="",
            skipped=True,
            crashed=True,
            skip_reason=repr(e),
        )
    else:
        res = safe_analyze(layer, diff, metadata)
    if on_progress:
        try:
            status = "done" if not res.skipped else "skip"
            on_progress(name, status)
        except Exception:  # noqa: BLE001
            pass
    return res


def run_analysis(
    diff: NormalizedDiff,
    metadata: dict[str, object],
    config: WatchGateConfig,
    layer_factories: dict[str, LayerFactory] | None = None,
    on_progress: ProgressCallback | None = None,
) -> AggregatedResult:
    """Instancia las capas activas (peso > 0 y registradas), las ejecuta en
    paralelo con `safe_analyze` y agrega el resultado final.

    `layer_factories` es opcional y no rompe la regla de arriba: sigue sin
    haber ningún `if` que decida *qué* capa ejecutar por nombre, solo *cómo*
    construir la instancia de una que ya se decidió ejecutar. Hace falta
    porque no todas las capas admiten `LAYER_REGISTRY[name]()` sin más --
    `SemanticLayer` exige `llm_client`/`cost_control` en el constructor (sin
    esto, instanciarla revienta con TypeError; reproducido en la revisión).
    Quien invoque `run_analysis` (el adaptador de plataforma) pasa aquí cómo
    construir esas capas; si no se pasa nada para una capa, se usa
    `LAYER_REGISTRY[name]()` como hasta ahora (compatible con capas sin
    dependencias, como `ReputationLayer`).
    """

    def _registry_factory(_name: str) -> LayerFactory:
        return lambda: LAYER_REGISTRY[_name]()

    factories = layer_factories or {}
    active_layer_specs: list[tuple[str, LayerFactory]] = [
        (name, factories[name] if name in factories else _registry_factory(name))
        for name, weight in config.weights.items()
        if weight > 0 and name in LAYER_REGISTRY
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(active_layer_specs) or 1) as pool:
        futures = {
            pool.submit(_build_and_analyze, name, factory, diff, metadata, on_progress): name
            for name, factory in active_layer_specs
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
