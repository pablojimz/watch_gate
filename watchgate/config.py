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
import math
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from watchgate.core.aggregator import DEFAULT_THRESHOLDS

logger = logging.getLogger("watchgate.config")

# Pesos por defecto. El ejemplo de regresión de la memoria (spec §10) fija
# estos cuatro: static=0.25, dependencies=0.20, reputation=0.15,
# semantic=0.40 -- al añadir "vulnerabilities" (CVEs conocidas vía OSV,
# separada de "dependencies" para poder desactivarla sin perder las señales
# de ataque a la cadena de suministro) se reparte a la mitad el 0.20 que
# antes tenía solo "dependencies", dejando el resto exactamente igual que
# en la memoria.
DEFAULT_WEIGHTS: dict[str, float] = {
    "static": 0.25,
    "dependencies": 0.10,
    "vulnerabilities": 0.10,
    "reputation": 0.15,
    "semantic": 0.40,
}

_DEFAULT_THRESHOLDS: dict[str, int] = DEFAULT_THRESHOLDS


class WatchGateConfig(BaseSettings):
    """Configuración completa de WatchGate.

    Cumple estructuralmente el `Protocol WatchGateConfig` que define
    `orchestrator.py` (mismos atributos `weights`/`thresholds`); no hace
    falta que `orchestrator.py` importe esta clase directamente.
    """

    model_config = SettingsConfigDict(env_prefix="WATCHGATE_", extra="ignore")

    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    thresholds: dict[str, int] = Field(default_factory=lambda: dict(_DEFAULT_THRESHOLDS))

    @field_validator("weights", mode="before")
    @classmethod
    def _normalize_weights(cls, v: Any) -> Any:
        if isinstance(v, dict):
            if "deps" in v and "dependencies" not in v:
                v["dependencies"] = v.pop("deps")
        return v

    @field_validator("weights")
    @classmethod
    def _validate_weights(cls, v: dict[str, float]) -> dict[str, float]:
        """Auditoría: `load_config` no validaba los VALORES de `weights` en
        absoluto -- solo `apply_cli_overrides` (overrides de línea de
        comandos) comprobaba que sumaran > 0. Un `.watchgate.yml` con un
        peso mal escrito (PyYAML parsea `.inf` como `float("inf")`) hacía
        que `weighted_average()` calculara `inf * risk_score_0 = nan`, y
        `round(nan)` en `aggregator.aggregate()` revienta con `ValueError`
        sin capturar -- ni siquiera hace falta un YAML "malicioso", un
        typo humano (`.inf` en vez de `1`) ya lo dispara. Un peso negativo
        rompería igualmente el contrato "el score final está entre 0 y
        100" en el que confía el resto del pipeline. Alcance: solo afecta
        al camino de CLI local contra un checkout propio (el Engine API
        de producción carga su propia config, no la de un PR ajeno), pero
        fallar rápido aquí es más barato que un traceback a mitad de
        análisis."""
        for name, weight in v.items():
            if not math.isfinite(weight):
                raise ValueError(f"weights['{name}']={weight!r} no es un número finito")
            if weight < 0:
                raise ValueError(f"weights['{name}']={weight!r} no puede ser negativo")
        return v

    # Usados por cost_control.py (§8).
    max_diff_tokens: int = 8000
    monthly_budget_tokens: int | None = 2_000_000

    # Usado por vulnerabilities_layer.py (§5) como VulnerabilitiesLayer.max_osv_queries
    # -- cuántos paquetes NUEVOS de un mismo diff se consultan contra OSV.dev
    # como máximo. Subido de 20 a 5000 a petición explícita ("un número
    # enorme") -- ver el comentario de _HARD_MAX_BATCH_SIZE en
    # vulnerabilities_layer.py sobre por qué 5000 sigue siendo seguro (las
    # peticiones HTTP van troceadas en paralelo, no en un único lote).
    max_dependency_checks: int = 5000

    # Usado por el adaptador de GitHub Action (§12).
    block_on_red: bool = True

    # Usado por shortcircuit.py (§11, opcional).
    shortcircuit_enabled: bool = False

    # Configuración de VCS / GitHub API
    github_token: str | None = Field(default=None, validation_alias="WATCHGATE_GITHUB_TOKEN")
    github_api_url: str = Field(
        default="https://api.github.com", validation_alias="WATCHGATE_GITHUB_API_URL"
    )


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
            f"{yaml_path}: se esperaba un mapeo YAML en la raíz, se encontró {type(data).__name__}"
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
        **{
            **config.model_dump(),
            "weights": weights,
            "thresholds": thresholds,
        }
    )
