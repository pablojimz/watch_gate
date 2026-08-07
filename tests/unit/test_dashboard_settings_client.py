"""Tests de watchgate/adapters/github_action/dashboard_settings_client.py.

Cierra el hueco simétrico a dashboard_client.py: antes de esto, "Configuración"
en el dashboard (pesos, umbrales, capas activas, política de bloqueo,
presupuesto de LLM) no lo leía nadie -- la Action solo usaba .watchgate.yml.
Cubre en particular la traducción entre la convención de nombres propia del
dashboard ("deps", "amarillo"/"rojo") y la del motor ("dependencies",
"yellow"/"red"), que nunca se había necesitado porque nunca se conectaban.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from watchgate.adapters.github_action.dashboard_settings_client import apply_dashboard_config
from watchgate.config import WatchGateConfig


def _fake_ci_config_response(**overrides: object) -> MagicMock:
    body = {
        "weights": {"static": 0.25, "deps": 0.25, "reputation": 0.15, "semantic": 0.35},
        "thresholds": {"amarillo": 30, "rojo": 80},
        "layers_enabled": {"static": True, "deps": True, "reputation": True, "semantic": True},
        "block_on_high": True,
        "monthly_budget_tokens": 500_000,
        "max_diff_tokens": 40_000,
        **overrides,
    }
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = body
    return response


def test_does_nothing_when_dashboard_url_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_DASHBOARD_URL", raising=False)
    config = WatchGateConfig()
    with patch(
        "watchgate.adapters.github_action.dashboard_settings_client.httpx.get"
    ) as mock_get:
        result = apply_dashboard_config(config, "acme/payments-api")
    mock_get.assert_not_called()
    assert result is config


def test_falls_back_to_original_config_on_http_error(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com")
    config = WatchGateConfig()
    with patch(
        "watchgate.adapters.github_action.dashboard_settings_client.httpx.get",
        side_effect=httpx.ConnectError("no se pudo conectar"),
    ):
        result = apply_dashboard_config(config, "acme/payments-api")
    assert result.weights == config.weights
    assert result.thresholds == config.thresholds


def test_translates_deps_key_to_dependencies(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com")
    with patch(
        "watchgate.adapters.github_action.dashboard_settings_client.httpx.get",
        return_value=_fake_ci_config_response(),
    ):
        result = apply_dashboard_config(WatchGateConfig(), "acme/payments-api")
    assert result.weights["dependencies"] == 0.25
    assert "deps" not in result.weights


def test_translates_spanish_threshold_keys_to_english(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com")
    with patch(
        "watchgate.adapters.github_action.dashboard_settings_client.httpx.get",
        return_value=_fake_ci_config_response(),
    ):
        result = apply_dashboard_config(WatchGateConfig(), "acme/payments-api")
    assert result.thresholds == {"yellow": 30, "red": 80}


def test_disabled_layer_gets_zero_weight() -> None:
    from watchgate.adapters.github_action.dashboard_settings_client import (
        _weights_with_disabled_layers_zeroed,
    )

    weights = {"static": 0.25, "deps": 0.25, "reputation": 0.15, "semantic": 0.35}
    layers_enabled = {"static": True, "deps": False, "reputation": True, "semantic": True}
    result = _weights_with_disabled_layers_zeroed(weights, layers_enabled)
    assert result["deps"] == 0.0
    assert result["static"] == 0.25


def test_disabled_layer_ends_up_excluded_from_the_final_config(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com")
    with patch(
        "watchgate.adapters.github_action.dashboard_settings_client.httpx.get",
        return_value=_fake_ci_config_response(
            layers_enabled={
                "static": True,
                "deps": False,
                "reputation": True,
                "semantic": True,
            }
        ),
    ):
        result = apply_dashboard_config(WatchGateConfig(), "acme/payments-api")
    assert result.weights["dependencies"] == 0.0


def test_applies_block_on_high_and_llm_budget_fields(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com")
    with patch(
        "watchgate.adapters.github_action.dashboard_settings_client.httpx.get",
        return_value=_fake_ci_config_response(block_on_high=False),
    ):
        result = apply_dashboard_config(WatchGateConfig(), "acme/payments-api")
    assert result.block_on_red is False
    assert result.monthly_budget_tokens == 500_000
    assert result.max_diff_tokens == 40_000


def test_sends_bearer_token_and_repo_scoped_url(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com/")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "secreto-ci")
    with patch(
        "watchgate.adapters.github_action.dashboard_settings_client.httpx.get",
        return_value=_fake_ci_config_response(),
    ) as mock_get:
        apply_dashboard_config(WatchGateConfig(), "acme/payments-api")
    args, kwargs = mock_get.call_args
    assert args[0] == "https://dashboard.example.com/api/repos/acme/payments-api/ci-config"
    assert kwargs["headers"]["Authorization"] == "Bearer secreto-ci"
