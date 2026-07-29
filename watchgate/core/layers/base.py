"""Interfaz común de capa + LAYER_REGISTRY (A.0.0).

Ver docs/WatchGate_spec_implementacion_IA.md §3.

El orquestador nunca importa una capa concreta por nombre: solo instancia
desde LAYER_REGISTRY según las claves con peso > 0 en la config. Esto es lo
que garantiza "activación selectiva" y "extensión sin reescritura".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from watchgate.core.models import LayerResult, NormalizedDiff


class AnalysisLayer(ABC):
    name: str  # debe coincidir con la clave usada en .watchgate.yml -> weights

    @abstractmethod
    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        """Debe devolver siempre un LayerResult válido, nunca lanzar excepción
        no controlada. Cualquier error interno se captura y se traduce en
        LayerResult(skipped=True, skip_reason=str(e), risk_score=0)."""


LAYER_REGISTRY: dict[str, type[AnalysisLayer]] = {}


def register_layer(cls: type[AnalysisLayer]) -> type[AnalysisLayer]:
    """Decorador: da de alta la capa en LAYER_REGISTRY bajo su `cls.name`."""
    LAYER_REGISTRY[cls.name] = cls
    return cls


def safe_analyze(
    layer: AnalysisLayer, diff: NormalizedDiff, metadata: dict[str, Any]
) -> LayerResult:
    """Wrapper de ejecución segura, usado en el orquestador (no en cada capa)."""
    try:
        return layer.analyze(diff, metadata)
    except Exception as e:  # noqa: BLE001 - frontera de aislamiento entre capas
        return LayerResult(
            layer_name=layer.name,
            risk_score=0,
            justification="",
            skipped=True,
            skip_reason=repr(e),
        )
