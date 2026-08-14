"""Tests de pipeline.py (§9/§12): wiring real de run_full_analysis."""

from __future__ import annotations

from watchgate.config import WatchGateConfig
from watchgate.core.layers._semantic.layer import SemanticLayer
from watchgate.core.layers.reputation_layer import ReputationLayer
from watchgate.core.models import LayerResult, NormalizedDiff, ReputationMetadata
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


def test_shortcircuit_enabled_does_not_rerun_non_semantic_layers_when_it_does_not_fire(
    monkeypatch, tmp_path
):
    """Regresión: con `shortcircuit_enabled=True` y el cortocircuito sin
    dispararse, el pipeline llamaba `run_analysis()` completo una SEGUNDA
    vez -- reejecutando desde cero las capas no-semánticas que ya se habían
    ejecutado para calcular `partial_res` (subprocesos de Semgrep, consultas
    OSV, llamadas de red de reputación), sin ningún beneficio: el
    cortocircuito existe para ahorrarse la llamada al LLM, no para duplicar
    el resto del trabajo cuando no se dispara. Solo la capa semántica debe
    ejecutarse de nuevo."""
    monkeypatch.chdir(tmp_path)

    reputation_calls: list[None] = []
    original_analyze = ReputationLayer.analyze

    def _counting_analyze(
        self: ReputationLayer,
        diff: NormalizedDiff,
        metadata: dict,  # type: ignore[type-arg]
    ) -> LayerResult:
        reputation_calls.append(None)
        return original_analyze(self, diff, metadata)

    monkeypatch.setattr(ReputationLayer, "analyze", _counting_analyze)

    semantic_calls: list[None] = []

    def _fake_semantic_analyze(
        self: SemanticLayer, diff: NormalizedDiff, metadata: dict
    ) -> LayerResult:  # type: ignore[type-arg]
        semantic_calls.append(None)
        return LayerResult(layer_name="semantic", risk_score=10, justification="benigno")

    monkeypatch.setattr(SemanticLayer, "analyze", _fake_semantic_analyze)

    # Cuenta de 5 días + sin contribuciones previas = risk_score 50 (spec §6:
    # +30 cuenta<30 días, +20 sin contribuciones) -- ni tan bajo que dispare
    # el atajo a VERDE (partial_score < umbral_amarillo*0.5) ni tan alto que
    # dispare el atajo a ROJO (con semantic=0 la media ponderada mínima
    # posible sigue por debajo del umbral rojo), así que `evaluate_
    # shortcircuit` cae al `return None` final -- el caso real más común,
    # ni claramente limpio ni claramente sucio.
    config = WatchGateConfig(
        weights={"reputation": 1.0, "semantic": 1.0},
        shortcircuit_enabled=True,
    )
    metadata = {
        "repo": "owner/repo",
        "reputation": ReputationMetadata(
            author_login="newbie",
            author_account_age_days=5,
            author_prior_contributions_to_repo=0,
            commit_email_matches_verified_email=True,
            commit_is_signed=False,
            signing_key_seen_before_for_login=None,
            repo_has_history_of_signed_commits=False,
        ),
    }

    result = run_full_analysis(_empty_diff(), metadata, config)

    assert (
        len(reputation_calls) == 1
    ), f"reputation.analyze() se llamó {len(reputation_calls)} veces, se esperaba 1"
    assert len(semantic_calls) == 1
    assert result.layer_results["reputation"].risk_score == 50
    assert result.layer_results["semantic"].risk_score == 10
