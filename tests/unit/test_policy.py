"""Tests de watchgate/service/policy.py.

Cubre dos mecanismos distintos con niveles de confianza distintos:
- `apply_client_config_override`: config_override de una petición HTTP de
  un agente de IA -- NO confiable, debe rechazar campos de seguridad.
- `PolicyService.apply_policy_overrides`: policy_json de una Organización
  -- fuente de confianza (un administrador), pero igualmente debe validar
  rangos y no tumbar el análisis si queda mal formado.
"""

from __future__ import annotations

import json

import pytest

from watchgate.config import WatchGateConfig
from watchgate.db.models import Organization
from watchgate.service.policy import (
    ClientConfigOverrideError,
    PolicyService,
    apply_client_config_override,
)


def _base_config() -> WatchGateConfig:
    # Suma 1.0 a propósito -- si no, `apply_policy_overrides` renormaliza
    # incluso cuando ningún override se llega a aplicar de verdad, lo que
    # haría los tests de "se ignora el valor fuera de rango" frágiles.
    return WatchGateConfig(
        weights={"static": 0.25, "dependencies": 0.20, "reputation": 0.15, "semantic": 0.40},
        thresholds={"yellow": 40, "red": 70},
    )


@pytest.mark.parametrize(
    "forbidden_override",
    [
        {"thresholds": {"yellow": 999, "red": 999}},
        {"weights": {"semantic": 0.0}},
        {"block_on_red": False},
        {"shortcircuit_enabled": False},
    ],
)
def test_client_override_rejects_security_fields(forbidden_override):
    """Caso real que motivó este fix: un agente de IA podía autoaprobar su
    propio PR malicioso mandando config_override:
    {"thresholds": {"yellow": 999, "red": 999}} -- el resultado siempre
    daba verde. Estos 4 campos deciden si un PR se marca rojo y si eso
    bloquea el merge, así que una petición HTTP nunca puede tocarlos."""
    with pytest.raises(ClientConfigOverrideError):
        apply_client_config_override(_base_config(), forbidden_override)


def test_client_override_allows_non_security_fields():
    config = apply_client_config_override(_base_config(), {"max_diff_tokens": 4000})
    assert config.max_diff_tokens == 4000
    # Los campos de seguridad no se tocaron.
    assert config.thresholds == {"yellow": 40, "red": 70}


def test_client_override_none_or_empty_is_noop():
    base = _base_config()
    assert apply_client_config_override(base, None) is base
    assert apply_client_config_override(base, {}) is base


def test_policy_service_ignores_out_of_range_weight():
    org = Organization(
        id="org1",
        name="Acme",
        policy_json=json.dumps({"weights": {"static": -1.0}}),
    )
    config = PolicyService.apply_policy_overrides(_base_config(), org)
    # El peso negativo se descarta -- no debe colarse en la config efectiva.
    assert config.weights["static"] != -1.0
    assert config.weights["static"] == pytest.approx(0.25)


def test_policy_service_ignores_out_of_range_threshold():
    org = Organization(
        id="org1",
        name="Acme",
        policy_json=json.dumps({"thresholds": {"red": 999}}),
    )
    config = PolicyService.apply_policy_overrides(_base_config(), org)
    assert config.thresholds["red"] == 70


def test_policy_service_falls_back_to_base_config_on_malformed_result():
    """policy_json sintácticamente válido pero con un tipo incorrecto no
    debe tumbar el análisis de toda la organización con un 500 sin
    capturar -- debe ignorar la política corrupta y seguir con la config
    base hasta que se corrija."""
    org = Organization(
        id="org1",
        name="Acme",
        policy_json=json.dumps({"monthly_budget_tokens": "unlimited"}),
    )
    base = _base_config()
    config = PolicyService.apply_policy_overrides(base, org)
    assert config == base


def test_policy_service_applies_valid_overrides_within_range():
    org = Organization(
        id="org1",
        name="Acme",
        policy_json=json.dumps({"thresholds": {"red": 60}, "block_on_red": False}),
    )
    config = PolicyService.apply_policy_overrides(_base_config(), org)
    assert config.thresholds["red"] == 60
    assert config.block_on_red is False


def test_policy_service_noop_without_policy_json():
    base = _base_config()
    assert PolicyService.apply_policy_overrides(base, None) is base
    assert PolicyService.apply_policy_overrides(base, Organization(id="o", name="N")) is base
