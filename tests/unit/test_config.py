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
