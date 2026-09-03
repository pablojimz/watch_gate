"""Tests de watchgate/core/layers/reputation_layer.py (spec §6)."""

from watchgate.core.layers.reputation_layer import ReputationLayer
from watchgate.core.models import NormalizedDiff, ReputationMetadata


def _empty_diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a" * 40,
        head_sha="a" * 40,
        repo_path="/tmp/repo",
        files=[],
        commit_messages=[],
        authors=[],
    )


def _clean_reputation(**overrides: object) -> ReputationMetadata:
    base = dict(
        author_login="ana",
        author_account_age_days=400,
        author_prior_contributions_to_repo=12,
        commit_email_matches_verified_email=True,
        commit_is_signed=True,
        signing_key_seen_before_for_login=True,
        repo_has_history_of_signed_commits=True,
    )
    base.update(overrides)
    return ReputationMetadata(**base)


def test_skips_when_no_reputation_metadata_present():
    result = ReputationLayer().analyze(_empty_diff(), {})
    assert result.skipped is True
    assert result.skip_reason == "Sin metadatos de plataforma disponibles"
    assert result.risk_score == 0


def test_skips_when_reputation_key_has_wrong_type():
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": {"not": "a model"}})
    assert result.skipped is True


def test_accepts_valid_dict_reputation():
    rep_dict = _clean_reputation().model_dump()
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": rep_dict})
    assert result.skipped is False
    assert result.risk_score == 0


def test_no_signals_gives_zero_risk_and_clean_justification():
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": _clean_reputation()})
    assert result.skipped is False
    assert result.risk_score == 0
    assert "no se han detectado" in result.justification.lower()


def test_atomic_arch_simulated_case_scores_at_least_55():
    """Test de aceptación de la spec original: cuenta de 2 días, 0
    contribuciones, email no verificado -> risk_score >= 75 (30 + 20 + 25).

    Decisión de producto posterior: 20 de los 30 puntos de "cuenta nueva" se
    movieron a la señal nueva `author_has_prior_high_risk_pr` (ver esa
    señal más abajo) -- una cuenta nueva sigue siendo sospechosa (+10), pero
    un autor con un ataque previo YA confirmado en otro repo pesa más que la
    mera edad de la cuenta. Este caso sin esa señal (nunca se resolvió el
    historial) baja a 55 (10 + 20 + 25); el umbral >=75 original ya no
    aplica sin ella."""
    reputation = _clean_reputation(
        author_account_age_days=2,
        author_prior_contributions_to_repo=0,
        commit_email_matches_verified_email=False,
        commit_is_signed=False,
        signing_key_seen_before_for_login=None,
        repo_has_history_of_signed_commits=False,
    )
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": reputation})
    assert result.risk_score >= 55
    assert "2 días" in result.justification
    assert "no tiene contribuciones previas" in result.justification.lower()
    assert "no coincide con un email verificado" in result.justification.lower()


def test_new_account_alone_adds_10():
    reputation = _clean_reputation(author_account_age_days=5)
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": reputation})
    assert result.risk_score == 10
    assert "5 días" in result.justification


def test_prior_high_risk_pr_saturates_to_100():
    """Señal nueva: un autor con un PR anterior ya detectado con score >= 70
    (en cualquier repo, no solo el actual) satura la capa entera a 100 --
    ya no suma puntos como el resto de señales, se considera suficiente por
    sí sola. Se resuelve fuera de esta capa (dashboard/backend/tasks.py, vía
    db.py::author_has_prior_high_risk_pr) y llega ya resuelta en el campo
    homónimo de ReputationMetadata."""
    reputation = _clean_reputation(author_has_prior_high_risk_pr=True)
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": reputation})
    assert result.risk_score == 100
    assert "PR anterior detectado" in result.justification


def test_prior_high_risk_pr_defaults_to_false_and_does_not_fire():
    """El default de la señal (False) no debe disparar nada por sí solo --
    solo dispara si algo aguas arriba la puso a True explícitamente."""
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": _clean_reputation()})
    assert result.risk_score == 0
    assert "PR anterior" not in result.justification


def test_repo_signs_but_commit_is_not_signed_adds_30():
    reputation = _clean_reputation(
        commit_is_signed=False,
        signing_key_seen_before_for_login=None,
        repo_has_history_of_signed_commits=True,
    )
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": reputation})
    assert result.risk_score == 30
    assert "no está firmado" in result.justification


def test_signed_with_key_never_seen_before_adds_40():
    reputation = _clean_reputation(signing_key_seen_before_for_login=False)
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": reputation})
    assert result.risk_score == 40
    assert "nunca se había visto antes" in result.justification


def test_score_is_capped_at_100():
    reputation = _clean_reputation(
        author_account_age_days=1,
        author_public_repos=0,
        author_followers=0,
        author_prior_contributions_to_repo=0,
        commit_email_matches_verified_email=False,
        commit_is_signed=True,
        signing_key_seen_before_for_login=False,
    )
    # 10 (edad) + 15 (sin actividad pública) + 20 (sin contribuciones) +
    # 25 (email) + 40 (clave de firma nunca vista) = 110 -> tope 100.
    # Deliberadamente sin author_has_prior_high_risk_pr, que ya no suma
    # puntos sino que satura la capa por su cuenta (ver test
    # test_prior_high_risk_pr_saturates_to_100).
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": reputation})
    assert result.risk_score == 100


def test_prior_high_risk_pr_saturates_even_with_no_other_signals():
    """La saturación a 100 no depende de que se acumulen otras señales --
    dispara sola, sin necesidad de sumar nada más."""
    reputation = _clean_reputation(
        author_account_age_days=400,
        author_prior_contributions_to_repo=12,
        commit_email_matches_verified_email=True,
        author_has_prior_high_risk_pr=True,
    )
    result = ReputationLayer().analyze(_empty_diff(), {"reputation": reputation})
    assert result.risk_score == 100
