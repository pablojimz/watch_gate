"""Tests de orchestrator.py (spec §9)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from watchgate.core.layers.base import LAYER_REGISTRY, AnalysisLayer, register_layer
from watchgate.core.models import LayerResult, NormalizedDiff
from watchgate.core.orchestrator import run_analysis


@dataclass
class FakeConfig:
    weights: dict[str, float]
    thresholds: dict[str, int] = field(default_factory=lambda: {"yellow": 40, "red": 70})


@pytest.fixture(autouse=True)
def _clean_registry():
    """Evita que capas fake registradas en un test contaminen otros tests
    (LAYER_REGISTRY es un dict global compartido)."""
    before = dict(LAYER_REGISTRY)
    yield
    LAYER_REGISTRY.clear()
    LAYER_REGISTRY.update(before)


def _empty_diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a", head_sha="b", repo_path=".", files=[], commit_messages=[], authors=[]
    )


def test_layers_run_in_parallel_not_sequentially():
    latency = 0.5

    def make_layer(layer_name: str, sleep_seconds: float) -> type[AnalysisLayer]:
        @register_layer
        class _Layer(AnalysisLayer):
            name = layer_name

            def analyze(self, diff, metadata):  # noqa: ANN001
                time.sleep(sleep_seconds)
                return LayerResult(layer_name=self.name, risk_score=10, justification="ok")

        return _Layer

    make_layer("fake_a", latency)
    make_layer("fake_b", latency)
    make_layer("fake_c", latency)
    make_layer("fake_d", latency)

    config = FakeConfig(weights={"fake_a": 0.25, "fake_b": 0.25, "fake_c": 0.25, "fake_d": 0.25})

    start = time.monotonic()
    result = run_analysis(_empty_diff(), metadata={"pr_id": "1", "repo": "org/repo"}, config=config)
    elapsed = time.monotonic() - start

    assert elapsed < latency * 2  # en paralelo ~0.5s, en secuencial sería ~2s
    assert set(result.layer_results.keys()) == {"fake_a", "fake_b", "fake_c", "fake_d"}


def test_only_layers_with_weight_greater_than_zero_run():
    @register_layer
    class _Active(AnalysisLayer):
        name = "fake_active"

        def analyze(self, diff, metadata):  # noqa: ANN001
            return LayerResult(layer_name=self.name, risk_score=50, justification="ok")

    @register_layer
    class _Inactive(AnalysisLayer):
        name = "fake_inactive"

        def analyze(self, diff, metadata):  # noqa: ANN001
            raise AssertionError("esta capa no debería ejecutarse (peso 0)")

    config = FakeConfig(weights={"fake_active": 1.0, "fake_inactive": 0.0})

    result = run_analysis(_empty_diff(), metadata={"pr_id": "1", "repo": "org/repo"}, config=config)

    assert set(result.layer_results.keys()) == {"fake_active"}


def test_layer_that_raises_is_isolated_via_safe_analyze():
    @register_layer
    class _Broken(AnalysisLayer):
        name = "fake_broken"

        def analyze(self, diff, metadata):  # noqa: ANN001
            raise RuntimeError("fallo simulado de la capa")

    config = FakeConfig(weights={"fake_broken": 1.0})

    result = run_analysis(_empty_diff(), metadata={"pr_id": "1", "repo": "org/repo"}, config=config)

    layer_result = result.layer_results["fake_broken"]
    assert layer_result.skipped is True
    assert "fallo simulado" in layer_result.skip_reason
