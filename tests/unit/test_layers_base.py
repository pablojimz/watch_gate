"""Tests de watchgate/core/layers/base.py (spec §3)."""

import pytest

from watchgate.core.layers.base import LAYER_REGISTRY, AnalysisLayer, register_layer, safe_analyze
from watchgate.core.models import LayerResult, NormalizedDiff


def _empty_diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a" * 40,
        head_sha="a" * 40,
        repo_path="/tmp/repo",
        files=[],
        commit_messages=[],
        authors=[],
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    """El registro es un dict a nivel de módulo: aislar cada test."""
    before = dict(LAYER_REGISTRY)
    LAYER_REGISTRY.clear()
    yield
    LAYER_REGISTRY.clear()
    LAYER_REGISTRY.update(before)


def test_register_layer_populates_registry_only_via_decorator():
    @register_layer
    class DummyLayer(AnalysisLayer):
        name = "dummy"

        def analyze(self, diff, metadata):
            return LayerResult(layer_name=self.name, risk_score=0, justification="ok")

    assert LAYER_REGISTRY["dummy"] is DummyLayer
    assert len(LAYER_REGISTRY) == 1


def test_analysis_layer_cannot_be_instantiated_without_analyze():
    with pytest.raises(TypeError):
        AnalysisLayer()  # type: ignore[abstract]


def test_safe_analyze_returns_result_when_layer_succeeds():
    class OkLayer(AnalysisLayer):
        name = "ok"

        def analyze(self, diff, metadata):
            return LayerResult(layer_name=self.name, risk_score=42, justification="hallazgo")

    result = safe_analyze(OkLayer(), _empty_diff(), {})
    assert result.risk_score == 42
    assert result.skipped is False


def test_safe_analyze_never_raises_and_marks_skipped_on_exception():
    class BoomLayer(AnalysisLayer):
        name = "boom"

        def analyze(self, diff, metadata):
            raise RuntimeError("fallo interno inesperado")

    result = safe_analyze(BoomLayer(), _empty_diff(), {})
    assert result.layer_name == "boom"
    assert result.skipped is True
    assert result.risk_score == 0
    assert "fallo interno inesperado" in result.skip_reason
