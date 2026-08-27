"""Tests de la purga de retención de pr_scores
(watchgate/dashboard/backend/db.py::delete_scores_older_than +
tasks.py::purge_old_scores) -- petición explícita: no acumular
histórico para siempre, purgar lo más antiguo que N días.
"""

from __future__ import annotations

from pathlib import Path

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
from watchgate.dashboard.backend import db as database


def _result(repo: str, pr_id: str, timestamp: str) -> AggregatedResult:
    return AggregatedResult(
        score=10,
        semaforo=Semaforo.VERDE,
        layer_results={
            "static": LayerResult(layer_name="static", risk_score=10, justification="x")
        },
        weights_used={"static": 1.0},
        pr_id=pr_id,
        repo=repo,
        timestamp=timestamp,
    )


def test_delete_scores_older_than_removes_only_old_rows(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("acme/app", "1", "2026-01-01T00:00:00+00:00"))
        recent_id = database.insert_aggregated(
            conn, _result("acme/app", "2", "2026-08-25T00:00:00+00:00")
        )

        deleted = database.delete_scores_older_than(conn, retention_days=30)

        assert deleted == 1
        remaining = database.list_scores(conn, "acme/app")
        assert [s.id for s in remaining] == [recent_id]


def test_delete_scores_older_than_is_a_noop_when_nothing_expired(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result("acme/app", "1", "2026-08-25T00:00:00+00:00"))

        deleted = database.delete_scores_older_than(conn, retention_days=30)

        assert deleted == 0
        assert len(database.list_scores(conn, "acme/app")) == 1


def test_purge_old_scores_task_calls_through_to_db(monkeypatch, tmp_path: Path) -> None:
    from watchgate.dashboard.backend import tasks

    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(db_path))

    with database.db_session(db_path) as conn:
        database.insert_aggregated(conn, _result("acme/app", "1", "2020-01-01T00:00:00+00:00"))

    tasks.purge_old_scores(30)

    with database.db_session(db_path) as conn:
        assert database.list_scores(conn, "acme/app") == []
