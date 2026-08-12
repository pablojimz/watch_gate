"""Tests de pipeline.py (§9/§12): wiring real de run_full_analysis."""

from __future__ import annotations

from watchgate.config import WatchGateConfig
from watchgate.core.models import NormalizedDiff
from watchgate.core.pipeline import run_full_analysis


def _empty_diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a", head_sha="b", repo_path=".", files=[], commit_messages=[], authors=[]
    )


def test_llm_client_init_error_surfaces_in_skip_reason_instead_of_being_swallowed(
    monkeypatch, tmp_path
):
    """Regresión: build_llm_client() se llamaba dentro de un `except Exception:
    llm_client = None` que descartaba el motivo real del fallo (p. ej. un
    WATCHGATE_LLM_PROVIDER/WATCHGATE_LLM_API_KEY mal combinados) -- el
    resultado quedaba indistinguible de "no hay configuración de LLM en
    absoluto". Ahora el motivo real debe llegar hasta el skip_reason de la
    capa semántica en el resultado final."""

    def _boom() -> None:
        raise ValueError(
            "WATCHGATE_LLM_PROVIDER='anthropic', pero WATCHGATE_LLM_API_KEY tiene el "
            "formato de una clave de 'gemini'"
        )

    monkeypatch.setattr("watchgate.core.pipeline.build_llm_client", _boom)
    monkeypatch.chdir(tmp_path)

    result = run_full_analysis(_empty_diff(), {"repo": "owner/repo"}, WatchGateConfig())

    semantic = result.layer_results["semantic"]
    assert semantic.skipped is True
    assert "WATCHGATE_LLM_PROVIDER" in semantic.skip_reason
    assert "formato de una clave de 'gemini'" in semantic.skip_reason
