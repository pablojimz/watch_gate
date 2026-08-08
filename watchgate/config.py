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

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("watchgate.config")

# Pesos por defecto. El ejemplo de regresión de la memoria (spec §10) fija
# estos cuatro: static=0.25, dependencies=0.20, reputation=0.15,
# semantic=0.40 -- al añadir "vulnerabilities" (CVEs conocidas vía OSV,
# separada de "dependencies" para poder desactivarla sin perder las señales
# de ataque a la cadena de suministro) se reparte a la mitad el 0.20 que
# antes tenía solo "dependencies", dejando el resto exactamente igual que
# en la memoria.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "static": 0.25,
    "dependencies": 0.10,
    "vulnerabilities": 0.10,
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

    @field_validator("weights", mode="before")
    @classmethod
    def _normalize_weights(cls, v: Any) -> Any:
        if isinstance(v, dict):
            if "deps" in v and "dependencies" not in v:
                v["dependencies"] = v.pop("deps")
        return v

    # Usados por cost_control.py (§8).
    max_diff_tokens: int = 8000
    monthly_budget_tokens: int | None = 2_000_000

    # Usado por deps_layer.py (§5).
    max_dependency_checks: int = 20

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


def apply_cli_overrides(
    config: WatchGateConfig,
    weight_overrides: list[str] | None = None,
    threshold_overrides: list[str] | None = None,
) -> WatchGateConfig:
    """Aplica overrides recibidos desde la CLI sobre la instancia de configuración.

    Si los pesos modificados no suman 1.0, se re-normalizan automáticamente
    y se emite una advertencia en el logger.
    """
    weights = dict(config.weights)
    thresholds = dict(config.thresholds)

    if weight_overrides:
        for override in weight_overrides:
            if "=" not in override:
                raise ValueError(
                    f"Formato de override de peso inválido: '{override}'. Usar 'capa=valor'"
                )
            key, val_str = override.split("=", 1)
            key = key.strip().lower()
            if key == "deps":
                key = "dependencies"
            try:
                val = float(val_str.strip())
            except ValueError as err:
                raise ValueError(f"Valor de peso inválido para '{key}': '{val_str}'") from err
            weights[key] = val

        # Normalización
        total_weight = sum(weights.values())
        if total_weight <= 0:
            raise ValueError("La suma de pesos debe ser mayor a 0")
        if abs(total_weight - 1.0) > 1e-4:
            logger.warning(
                "La suma de pesos CLI (%.2f) difiere de 1.0. Re-normalizando automáticamente.",
                total_weight,
            )
            weights = {k: round(v / total_weight, 4) for k, v in weights.items()}

    if threshold_overrides:
        for override in threshold_overrides:
            if "=" not in override:
                raise ValueError(
                    f"Formato de override de umbral inválido: '{override}'. Usar 'nivel=valor'"
                )
            key, val_str = override.split("=", 1)
            key = key.strip().lower()
            try:
                val = int(val_str.strip())
            except ValueError as err:
                raise ValueError(f"Valor de umbral inválido para '{key}': '{val_str}'") from err
            thresholds[key] = val

    return WatchGateConfig(
        weights=weights,
        thresholds=thresholds,
        max_diff_tokens=config.max_diff_tokens,
        monthly_budget_tokens=config.monthly_budget_tokens,
        max_dependency_checks=config.max_dependency_checks,
        block_on_red=config.block_on_red,
        shortcircuit_enabled=config.shortcircuit_enabled,
    )
