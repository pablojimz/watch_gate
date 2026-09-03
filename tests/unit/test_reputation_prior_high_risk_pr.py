"""Tests de watchgate/dashboard/backend/db.py::author_has_prior_high_risk_pr
-- señal de reputación nueva (ver core/layers/reputation_layer.py y
ReputationMetadata.author_has_prior_high_risk_pr): True si el autor tiene,
en cualquier repo auditado por este Dashboard, un PR anterior con
score >= 70."""

from __future__ import annotations

from pathlib import Path

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
from watchgate.dashboard.backend import db as database


def _result(pr_id: str, repo: str, score: int) -> AggregatedResult:
    return AggregatedResult(
        score=score,
        semaforo=Semaforo.ROJO if score >= 66 else Semaforo.VERDE,
        layer_results={
            "static": LayerResult(layer_name="static", risk_score=score, justification="")
        },
        weights_used={"static": 1.0},
        pr_id=pr_id,
        repo=repo,
        timestamp="2026-08-01T00:00:00+00:00",
    )


def test_true_when_author_has_a_prior_pr_above_threshold(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("1", "acme/repo-a", 85), author_login="mala")
        found = database.author_has_prior_high_risk_pr(conn, "mala")
    assert found is True


def test_false_when_no_prior_pr_above_threshold(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("1", "acme/repo-a", 50), author_login="ana")
        found = database.author_has_prior_high_risk_pr(conn, "ana")
    assert found is False


def test_false_for_author_with_no_history_at_all(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        found = database.author_has_prior_high_risk_pr(conn, "nadie")
    assert found is False


def test_true_across_different_repos(tmp_path: Path) -> None:
    """La señal es global: un ataque ya detectado en OTRO repo cuenta igual
    -- un autor no empieza "limpio" en cada repo nuevo que toca."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("9", "acme/other-repo", 90), author_login="mala")
        found = database.author_has_prior_high_risk_pr(
            conn, "mala", exclude_repo="acme/repo-a", exclude_pr_number=1
        )
    assert found is True


def test_excludes_the_pr_being_analyzed_right_now(tmp_path: Path) -> None:
    """Un re-análisis de la MISMA PR (mismo repo+pr_number, p. ej. tras un
    nuevo push) no debe autoflaggearse por su propia corrida anterior."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("4", "acme/repo-a", 93), author_login="mala")
        found = database.author_has_prior_high_risk_pr(
            conn, "mala", exclude_repo="acme/repo-a", exclude_pr_number=4
        )
    assert found is False
    # Pero SÍ cuenta para otra PR del mismo autor en ese mismo repo.
    with database.db_session(tmp_path / "dashboard.db") as conn:
        found_other_pr = database.author_has_prior_high_risk_pr(
            conn, "mala", exclude_repo="acme/repo-a", exclude_pr_number=5
        )
    assert found_other_pr is True


def test_min_score_is_inclusive_not_strictly_greater_than(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("1", "acme/repo-a", 70), author_login="ana")
        found = database.author_has_prior_high_risk_pr(conn, "ana", min_score=70)
    assert found is True
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("2", "acme/repo-a", 69), author_login="pepe")
        not_found = database.author_has_prior_high_risk_pr(conn, "pepe", min_score=70)
    assert not_found is False
