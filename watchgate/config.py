"""Configuración de WatchGate (spec §0).

Lee `.watchgate.yml` + variables de entorno (prefijo `WATCHGATE_`), con
validación de esquema en el arranque: si el YAML está mal formado, o si
algún valor no cumple el tipo esperado, `load_config` lanza en el momento de
llamarla (fallar rápido), no en mitad de un análisis.

Prioridad de valores (mayor a menor): valores del YAML > variables de
entorno > defaults de esta clase.

NOTA: este módulo no está asignado explícitamente a nadie en el reparto de
tareas del equipo (no aparece en plan_tareas_equipo.md). Lo implemento aquí
con una interfaz razonable para no bloquear `orchestrator.py`/`cost_control.py`,
pero debe confirmarse con el equipo — en particular los nombres de las claves
de `.watchgate.yml` y los valores por defecto de `thresholds`/`weights`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Pesos por defecto: iguales a los usados en el ejemplo de regresión de la
# memoria (spec §10) para las 4 capas conocidas hasta ahora.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "static": 0.25,
    "deps": 0.20,
    "reputation": 0.15,
    "semantic": 0.40,
}

_DEFAULT_THRESHOLDS: dict[str, int] = {"yellow": 40, "red": 70}


class WatchGateConfig(BaseSettings):
    """Configuración completa de WatchGate.

    Cumple estructuralmente el `Protocol WatchGateConfig` que define
    `orchestrator.py` (mismos atributos `weights`/`thresholds`); no hace
    falta que `orchestrator.py` importe esta clase directamente.
    """

    model_config = SettingsConfigDict(env_prefix="WATCHGATE_", extra="ignore")

    weights: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_WEIGHTS))
    thresholds: dict[str, int] = Field(default_factory=lambda: dict(_DEFAULT_THRESHOLDS))

    # Usados por cost_control.py (§8).
    max_diff_tokens: int = 8000
    monthly_budget_tokens: int = 2_000_000

    # Usado por el adaptador de GitHub Action (§12).
    block_on_red: bool = True

    # Usado por shortcircuit.py (§11, opcional).
    shortcircuit_enabled: bool = False


def _read_yaml(yaml_path: str) -> dict[str, Any]:
    path = Path(yaml_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(
            f"{yaml_path}: se esperaba un mapeo YAML en la raíz, "
            f"se encontró {type(data).__name__}"
        )
    return data


def load_config(yaml_path: str = ".watchgate.yml") -> WatchGateConfig:
    """Punto de entrada único para cargar la configuración.

    Falla rápido: si `.watchgate.yml` existe pero está mal formado (YAML
    inválido, o su raíz no es un mapeo), la excepción se propaga aquí, no en
    mitad de un análisis de PR. Un `.watchgate.yml` ausente no es un error:
    se usan defaults + variables de entorno.
    """
    yaml_data = _read_yaml(yaml_path)
    return WatchGateConfig(**yaml_data)
