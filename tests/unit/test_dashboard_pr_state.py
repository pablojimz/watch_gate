"""Tests de watchgate/dashboard/backend/db.py::mark_prs_closed y del wiring
en watchgate/service/repo_polling.py que oculta del dashboard las PRs que
ya se cerraron/mergearon en GitHub, sin borrar su histórico de análisis.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
from watchgate.dashboard.backend import db as database


def _result(repo: str, pr_id: str, score: int = 10) -> AggregatedResult:
    return AggregatedResult(
        score=score,
        semaforo=Semaforo.VERDE,
        layer_results={
            "static": LayerResult(layer_name="static", risk_score=score, justification="x")
        },
        weights_used={"static": 1.0},
        pr_id=pr_id,
        repo=repo,
        timestamp="2026-08-18T10:00:00+00:00",
    )


def test_new_pr_scores_default_to_open(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        score_id = database.insert_aggregated(conn, _result("acme/app", "1"))
        stored = database.get_score(conn, score_id)

    assert stored is not None
    assert stored.pr_state == "open"


def test_mark_prs_closed_updates_only_matching_open_rows(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        id_1 = database.insert_aggregated(conn, _result("acme/app", "1"))
        id_2 = database.insert_aggregated(conn, _result("acme/app", "2"))
        id_3 = database.insert_aggregated(conn, _result("acme/other", "1"))  # otro repo

        updated = database.mark_prs_closed(conn, "acme/app", {"1"})

        assert updated == 1
        assert database.get_score(conn, id_1).pr_state == "closed"  # type: ignore[union-attr]
        assert database.get_score(conn, id_2).pr_state == "open"  # type: ignore[union-attr]
        # Otro repo con el mismo número de PR no debe verse afectado.
        assert database.get_score(conn, id_3).pr_state == "open"  # type: ignore[union-attr]


def test_mark_prs_closed_never_touches_main_branch_scan(tmp_path: Path) -> None:
    """pr_number=0 (análisis de rama principal, pr_id='main') nunca es una
    PR real de GitHub -- no debe poder "cerrarse" aunque su número textual
    coincida por accidente con el de una PR real cerrada."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        main_id = database.insert_aggregated(conn, _result("acme/app", "main"))

        updated = database.mark_prs_closed(conn, "acme/app", {"0"})

        assert updated == 0
        assert database.get_score(conn, main_id).pr_state == "open"  # type: ignore[union-attr]


def test_mark_prs_closed_is_idempotent(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("acme/app", "5"))

        first = database.mark_prs_closed(conn, "acme/app", {"5"})
        second = database.mark_prs_closed(conn, "acme/app", {"5"})

    assert first == 1
    assert second == 0  # ya estaba "closed", no vuelve a contar


def test_mark_prs_closed_empty_input_is_a_noop(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.mark_prs_closed(conn, "acme/app", set()) == 0


def test_poll_single_candidate_marks_no_longer_open_prs_as_closed(tmp_path, monkeypatch) -> None:
    """Regresión: antes `_poll_single_candidate` solo usaba la lista de PRs
    abiertas de GitHub para encontrar PRs NUEVAS que encolar -- nunca
    comprobaba en sentido inverso qué PR ya trackeada dejó de estar en esa
    lista (se cerró/mergeó). Verifica el flujo completo vía el servicio
    real, con GitHub/Redis mockeados."""
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(tmp_path / "dashboard.db"))

    with database.db_session() as conn:
        # PR #1 ya analizada y trackeada en el dashboard; PR #2 sigue abierta.
        database.insert_aggregated(conn, _result("acme/app", "1"))
        database.insert_aggregated(conn, _result("acme/app", "2"))

    from watchgate.db.connection import SQLModel as EngineSQLModel
    from watchgate.db.connection import build_engine

    test_engine = build_engine(f"sqlite:///{tmp_path / 'engine.db'}")
    EngineSQLModel.metadata.create_all(test_engine)

    def _fake_get_session():
        from sqlmodel import Session

        session = Session(test_engine)
        try:
            yield session
        finally:
            session.close()

    with (
        patch("watchgate.service.repo_polling.get_session", _fake_get_session),
        patch("watchgate.dashboard.backend.tasks.get_session", _fake_get_session),
    ):
        fake_client = MagicMock()
        # Solo la PR #2 sigue abierta en GitHub -- la #1 se cerró/mergeó.
        fake_client.list_all_open_pull_requests.return_value = [{"number": 2}]
        fake_queue = MagicMock()
        fake_queue.fetch_job.return_value = None

        with (
            patch("watchgate.service.repo_polling.GitHubClient", return_value=fake_client),
            patch("watchgate.dashboard.backend.tasks.get_queue", return_value=fake_queue),
        ):
            from watchgate.service.repo_polling import RepoPollingService

            RepoPollingService._poll_single_candidate(
                {
                    "id": "repo-1",
                    "repo_path": "acme/app",
                    "org_id": "org-1",
                    "vcs_connection_id": None,
                    "prs_etag": None,
                    "token": None,
                }
            )

    with database.db_session() as conn:
        scores = {s.pr_id: s.pr_state for s in database.list_scores(conn, "acme/app")}

    assert scores["1"] == "closed"
    assert scores["2"] == "open"
