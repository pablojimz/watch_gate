"""Tests de config.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from watchgate.config import WatchGateConfig, load_config


def test_defaults_when_no_yaml_and_no_env(monkeypatch):
    monkeypatch.delenv("WATCHGATE_MAX_DIFF_TOKENS", raising=False)
    config = load_config(yaml_path="/nonexistent/.watchgate.yml")

    expected_weights = {
        "static": 0.25,
        "dependencies": 0.10,
        "vulnerabilities": 0.10,
        "reputation": 0.15,
        "semantic": 0.40,
    }
    assert config.weights == expected_weights
    assert config.thresholds == {"yellow": 40, "red": 70}
    assert config.max_diff_tokens == 8000
    assert config.block_on_red is True


def test_yaml_overrides_defaults():
    tmp_dir = tempfile.mkdtemp()
    yaml_path = Path(tmp_dir) / ".watchgate.yml"
    yaml_path.write_text("weights:\n  static: 0.5\n  deps: 0.5\nmax_diff_tokens: 1234\n")

    config = load_config(yaml_path=str(yaml_path))

    assert config.weights == {"static": 0.5, "dependencies": 0.5}
    assert config.max_diff_tokens == 1234
    # Lo no especificado en el YAML conserva el default.
    assert config.thresholds == {"yellow": 40, "red": 70}


def test_malformed_yaml_raises_immediately():
    tmp_dir = tempfile.mkdtemp()
    yaml_path = Path(tmp_dir) / ".watchgate.yml"
    yaml_path.write_text("weights: [this, is, not, a, mapping\n")  # YAML roto a propósito

    with pytest.raises(yaml.YAMLError):
        load_config(yaml_path=str(yaml_path))


def test_yaml_root_not_a_mapping_raises():
    tmp_dir = tempfile.mkdtemp()
    yaml_path = Path(tmp_dir) / ".watchgate.yml"
    yaml_path.write_text("- esto\n- es\n- una\n- lista\n")

    with pytest.raises(TypeError, match="mapeo YAML"):
        load_config(yaml_path=str(yaml_path))


def test_env_var_used_when_no_yaml_value(monkeypatch):
    monkeypatch.setenv("WATCHGATE_MAX_DIFF_TOKENS", "9999")
    config = load_config(yaml_path="/nonexistent/.watchgate.yml")

    assert config.max_diff_tokens == 9999


def test_yaml_wins_over_env_var(monkeypatch):
    monkeypatch.setenv("WATCHGATE_MAX_DIFF_TOKENS", "9999")
    tmp_dir = tempfile.mkdtemp()
    yaml_path = Path(tmp_dir) / ".watchgate.yml"
    yaml_path.write_text("max_diff_tokens: 111\n")

    config = load_config(yaml_path=str(yaml_path))

    assert config.max_diff_tokens == 111


def test_missing_yaml_file_is_not_an_error():
    config = load_config(yaml_path="/definitely/does/not/exist.yml")
    assert isinstance(config, WatchGateConfig)


def test_config_satisfies_orchestrator_protocol_structurally():
    """orchestrator.WatchGateConfig es un Protocol estructural: cualquier
    objeto con `weights`/`thresholds` sirve, incluida esta clase real."""
    from watchgate.core.orchestrator import WatchGateConfig as OrchestratorProtocol

    config = load_config(yaml_path="/nonexistent/.watchgate.yml")
    assert isinstance(config, OrchestratorProtocol)


def test_github_token_and_api_url_config(monkeypatch):
    monkeypatch.setenv("WATCHGATE_GITHUB_TOKEN", "gh_secret_123")
    monkeypatch.setenv("WATCHGATE_GITHUB_API_URL", "https://github.enterprise.local/api/v3")

    config = load_config(yaml_path="/nonexistent/.watchgate.yml")
    assert config.github_token == "gh_secret_123"
    assert config.github_api_url == "https://github.enterprise.local/api/v3"


# --- Auditoría: load_config() no validaba los VALORES de `weights` en
# absoluto. PyYAML parsea ".inf" como float("inf"); combinado con un
# risk_score=0 en weighted_average(), inf*0 = nan, y round(nan) en
# aggregator.aggregate() revienta con ValueError sin capturar a mitad de
# análisis en vez de fallar rápido al cargar la config.


def test_infinite_weight_from_yaml_is_rejected_at_load_time():
    """Reproduce el fallo real: `.watchgate.yml` con un peso `.inf` (typo
    humano plausible, PyYAML lo parsea como float("inf") sin protestar)
    -- antes esto no fallaba aquí, sino más tarde con un ValueError
    de round(nan) dentro del propio análisis."""
    tmp_dir = tempfile.mkdtemp()
    yaml_path = Path(tmp_dir) / ".watchgate.yml"
    yaml_path.write_text("weights:\n  static: .inf\n")

    with pytest.raises(Exception, match="no es un número finito"):
        load_config(yaml_path=str(yaml_path))


def test_negative_weight_from_yaml_is_rejected_at_load_time():
    tmp_dir = tempfile.mkdtemp()
    yaml_path = Path(tmp_dir) / ".watchgate.yml"
    yaml_path.write_text("weights:\n  static: -1\n")

    with pytest.raises(Exception, match="no puede ser negativo"):
        load_config(yaml_path=str(yaml_path))


def test_nan_weight_from_yaml_is_rejected_at_load_time():
    tmp_dir = tempfile.mkdtemp()
    yaml_path = Path(tmp_dir) / ".watchgate.yml"
    yaml_path.write_text("weights:\n  static: .nan\n")

    with pytest.raises(Exception, match="no es un número finito"):
        load_config(yaml_path=str(yaml_path))


def test_normal_weights_still_load_fine():
    """Red de seguridad del test anterior: confirma que la validación
    nueva no rechaza configuraciones normales."""
    config = WatchGateConfig(weights={"static": 0.25, "dependencies": 0.1, "semantic": 0.65})
    assert config.weights["static"] == 0.25
