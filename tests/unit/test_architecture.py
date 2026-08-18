"""Regla de arquitectura obligatoria (spec §3): core/ nunca importa
adapters/ ni dashboard/. Verificado con import-linter contra el contrato
"Layers" definido en pyproject.toml.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import importlinter.api  # noqa: F401 - el import dispara configuration.configure()
import pytest
from importlinter.application import use_cases

import watchgate.core.layers  # noqa: F401 - registrar capas en LAYER_REGISTRY
from watchgate.config import WatchGateConfig
from watchgate.core.layers.base import LAYER_REGISTRY
from watchgate.dashboard.backend.schemas import RepoSettings

CORE_DIR = Path(__file__).resolve().parents[2] / "watchgate" / "core"
VIOLATION_MODULE = CORE_DIR / "_tmp_architecture_violation.py"


def _run_lint() -> bool:
    return use_cases.lint_imports(verbose=False)


def test_core_does_not_import_adapters_or_dashboard():
    assert _run_lint() is True


def test_layer_names_consistency():
    """Garantiza la coincidencia exacta de nombres entre LAYER_REGISTRY,
    WatchGateConfig y RepoSettings sin mismatches ni desincronización.
    """
    registry_layers = set(LAYER_REGISTRY.keys())
    expected_layers = {"static", "dependencies", "vulnerabilities", "reputation", "semantic"}
    assert registry_layers == expected_layers, f"Capas registradas difieren: {registry_layers}"

    config_weights = set(WatchGateConfig().weights.keys())
    assert config_weights == expected_layers, f"Pesos de WatchGateConfig difieren: {config_weights}"

    # RepoSettings en el dashboard usa 'deps' como alias de 'dependencies'
    repo_settings = RepoSettings()
    dashboard_layers = {"dependencies" if k == "deps" else k for k in repo_settings.weights.keys()}
    assert dashboard_layers == expected_layers, (
        f"Pesos de RepoSettings difieren: {dashboard_layers}"
    )


def test_contract_actually_detects_a_violation():
    """Sin esto, el test anterior podría pasar solo porque nadie ha escrito
    código todavía, no porque el contrato funcione. Introducimos una
    violación real a propósito y comprobamos que el linter la atrapa."""
    VIOLATION_MODULE.write_text("import watchgate.dashboard.backend.main  # noqa: F401\n")
    try:
        importlib.invalidate_caches()
        assert _run_lint() is False
    finally:
        VIOLATION_MODULE.unlink()
        importlib.invalidate_caches()

    # Tras borrar la violación, el contrato vuelve a cumplirse.
    assert _run_lint() is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
