"""Aplica la configuración del dashboard (pesos, umbrales, capas, política
de bloqueo y presupuesto de LLM) al análisis de la Action, si el dashboard
está conectado (cierra el hueco simétrico a `dashboard_client.py`: ese
módulo manda datos Action -> Dashboard, este trae configuración Dashboard
-> Action).

Antes de esto, "Configuración" en el dashboard era un formulario que
guardaba en la base de datos y no lo leía nadie más -- un admin podía
cambiar pesos/umbrales/política y ver "Configuración guardada", sin que
ningún análisis real se viera afectado. `.watchgate.yml` seguía siendo la
única fuente de verdad real.

Opcional y resiliente, mismo criterio que `dashboard_client.py`: si
`WATCHGATE_DASHBOARD_URL` no está configurada, o la llamada falla, se
devuelve la config tal cual llegó (típicamente la de `.watchgate.yml`) sin
propagar la excepción -- un dashboard caído nunca debe impedir que el
análisis se complete.

Traducción de convenciones: el dashboard usa su propia convención de
nombres ("deps" en vez de "dependencies", "amarillo"/"rojo" en vez de
"yellow"/"red" -- consistente en todo `dashboard/backend/db.py`, nunca se
había necesitado traducir porque nunca se conectaba con el motor real).
`WatchGateConfig` ya sabe traducir "deps"->"dependencies" en su validador
de `weights` (`config.py::_normalize_weights`) siempre que se reconstruya
el objeto (no con `model_copy`, que no revalida) -- los umbrales no tienen
un validador equivalente, así que se traducen aquí a mano.
"""

from __future__ import annotations

import logging
import os

import httpx

from watchgate.config import WatchGateConfig

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0

_THRESHOLD_KEY_TRANSLATION = {"amarillo": "yellow", "rojo": "red"}


def _translate_thresholds(raw: dict[str, int]) -> dict[str, int]:
    return {_THRESHOLD_KEY_TRANSLATION.get(k, k): v for k, v in raw.items()}


def _weights_with_disabled_layers_zeroed(
    weights: dict[str, float], layers_enabled: dict[str, bool]
) -> dict[str, float]:
    merged = dict(weights)
    for layer_name, enabled in layers_enabled.items():
        if not enabled:
            merged[layer_name] = 0.0
    return merged


def apply_dashboard_config(config: WatchGateConfig, repo: str) -> WatchGateConfig:
    base_url = os.environ.get("WATCHGATE_DASHBOARD_URL")
    if not base_url:
        return config

    headers = {}
    token = os.environ.get("WATCHGATE_DASHBOARD_INGEST_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/repos/{repo}/ci-config",
            headers=headers,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.warning(
            "No se pudo obtener la configuración del dashboard para %s: %s -- "
            "se usa .watchgate.yml tal cual.",
            repo,
            exc,
        )
        return config

    merged = config.model_dump()

    weights = data.get("weights")
    layers_enabled = data.get("layers_enabled") or {}
    if weights:
        merged["weights"] = _weights_with_disabled_layers_zeroed(weights, layers_enabled)

    thresholds = data.get("thresholds")
    if thresholds:
        merged["thresholds"] = _translate_thresholds(thresholds)

    if data.get("block_on_high") is not None:
        merged["block_on_red"] = data["block_on_high"]
    if data.get("monthly_budget_tokens") is not None:
        merged["monthly_budget_tokens"] = data["monthly_budget_tokens"]
    if data.get("max_diff_tokens") is not None:
        merged["max_diff_tokens"] = data["max_diff_tokens"]

    # Reconstruir (no model_copy): hace falta que el validador de `weights`
    # de WatchGateConfig vuelva a correr para normalizar "deps" ->
    # "dependencies" -- model_copy() no revalida.
    return WatchGateConfig(**merged)
