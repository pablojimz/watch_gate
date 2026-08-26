"""Tests de la blacklist de autores (`core/pipeline.py::_check_blocked_author`
+ `dashboard/backend/routers/scores.py`): bloqueo manual por organización
que rechaza en rojo, sin ejecutar ninguna capa, antes de gastar presupuesto
de LLM.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from watchgate.core.models import FileChange, FileStatus, NormalizedDiff, Semaforo
from watchgate.core.pipeline import _check_blocked_author
from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.main import app
from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user, get_db_session
from watchgate.dashboard.backend.schemas import User as DashboardUser


@pytest.fixture
def _real_db(tmp_path, monkeypatch):
    """Mismo patrón que `test_repo_graph.py::_real_db` -- el pipeline usa
    `get_session()` real (no inyectable), así que se apunta a una sqlite
    temporal para el test."""
    from watchgate.db.connection import SQLModel, build_engine

    db_file = tmp_path / "test_blocked_authors.db"
    engine = build_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(engine)

    import watchgate.db.connection as db_connection

    monkeypatch.setattr(db_connection, "default_engine", engine)
    return engine


def _diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a" * 40,
        head_sha="b" * 40,
        repo_path="/tmp/no-existe",
        files=[
            FileChange(
                path="app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="+x = 1",
                additions=1,
                deletions=0,
            )
        ],
        commit_messages=["m"],
        authors=[],
    )


def test_check_blocked_author_returns_none_when_repo_unknown(_real_db):
    assert _check_blocked_author("no/existe", "cualquiera", "1") is None


def test_check_blocked_author_returns_none_when_author_not_blocked(_real_db):
    from watchgate.db.models import MonitoredRepo, Organization

    with Session(_real_db) as session:
        session.add(Organization(id="org-1", name="Org"))
        session.add(
            MonitoredRepo(id="repo-1", org_id="org-1", repo_path="acme/app", monitor_type="managed")
        )
        session.commit()

    assert _check_blocked_author("acme/app", "usuario-normal", "1") is None


def test_check_blocked_author_rejects_in_red_when_blocked(_real_db):
    from watchgate.db.models import BlockedAuthor, MonitoredRepo, Organization

    with Session(_real_db) as session:
        session.add(Organization(id="org-1", name="Org"))
        session.add(
            MonitoredRepo(id="repo-1", org_id="org-1", repo_path="acme/app", monitor_type="managed")
        )
        session.add(
            BlockedAuthor(
                id="block-1",
                org_id="org-1",
                author_login="atacante",
                reason="backdoor detectado el 2026-08-20",
                blocked_by="admin",
            )
        )
        session.commit()

    result = _check_blocked_author("acme/app", "atacante", "42")
    assert result is not None
    assert result.semaforo == Semaforo.ROJO
    assert result.score == 100
    assert result.pr_id == "42"
    assert "atacante" in result.layer_results["blocklist"].justification
    assert "backdoor detectado" in result.layer_results["blocklist"].justification


def test_check_blocked_author_is_scoped_by_organization(_real_db):
    """Un mismo login bloqueado en OTRA organización no debe afectar a esta."""
    from watchgate.db.models import BlockedAuthor, MonitoredRepo, Organization

    with Session(_real_db) as session:
        session.add(Organization(id="org-1", name="Org 1"))
        session.add(Organization(id="org-2", name="Org 2"))
        session.add(
            MonitoredRepo(id="repo-1", org_id="org-1", repo_path="acme/app", monitor_type="managed")
        )
        session.add(
            BlockedAuthor(
                id="block-1", org_id="org-2", author_login="dev", reason="x", blocked_by="admin"
            )
        )
        session.commit()

    assert _check_blocked_author("acme/app", "dev", "1") is None


def test_run_full_analysis_short_circuits_for_blocked_author(_real_db, monkeypatch):
    """Integración real: `run_full_analysis` no debe construir ninguna capa
    (ni siquiera intentar el LLM) si el autor está bloqueado."""
    from watchgate.config import WatchGateConfig
    from watchgate.core.pipeline import run_full_analysis
    from watchgate.db.models import BlockedAuthor, MonitoredRepo, Organization

    with Session(_real_db) as session:
        session.add(Organization(id="org-1", name="Org"))
        session.add(
            MonitoredRepo(id="repo-1", org_id="org-1", repo_path="acme/app", monitor_type="managed")
        )
        session.add(
            BlockedAuthor(
                id="block-1",
                org_id="org-1",
                author_login="atacante",
                reason="x",
                blocked_by="admin",
            )
        )
        session.commit()

    def _boom():
        raise AssertionError(
            "build_llm_client() no debía llamarse -- el bloqueo debe cortocircuitar antes"
        )

    monkeypatch.setattr("watchgate.core.pipeline.build_llm_client", _boom)

    config = WatchGateConfig()
    result = run_full_analysis(
        _diff(),
        metadata={"repo": "acme/app", "author_login": "atacante", "pr_id": "1"},
        config=config,
    )
    assert result.semaforo == Semaforo.ROJO
    assert result.score == 100


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    """Dos bases separadas, mismo criterio que el resto del proyecto: la
    inyectada vía `get_db_session` (SQLModel compartido con la Engine API
    -- `User`/`MonitoredRepo`/`BlockedAuthor`) para los datos del bloqueo,
    y `database.db_session()` (env `WATCHGATE_DASHBOARD_DB`) para la
    resolución de roles (`resolve_role` -> `repo_roles`), que son sistemas
    de persistencia distintos en este proyecto."""
    engine_db_path = tmp_path / "engine.db"
    engine = create_engine(f"sqlite:///{engine_db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import watchgate.db.connection as db_connection

    monkeypatch.setattr(db_connection, "default_engine", engine)

    dash_db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(dash_db_path))

    mock_user = DashboardUser(login="mantenedor_test")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: Session(engine)

    with Session(engine) as session:
        db_user = _get_or_create_db_user(session, "mantenedor_test")
        org_id = db_user.org_id
        session.commit()

        from watchgate.db.models import MonitoredRepo

        session.add(
            MonitoredRepo(
                id="repo-dash-1", org_id=org_id, repo_path="acme/dash-app", monitor_type="managed"
            )
        )
        session.commit()

    from watchgate.dashboard.backend import db as database

    with database.db_session(dash_db_path) as conn:
        database.upsert_role(conn, "mantenedor_test", "acme/dash-app", "mantenedor")

    client = TestClient(app)
    yield client, org_id
    app.dependency_overrides.clear()


def test_block_list_unblock_roundtrip_via_api(dashboard_client):
    client, _org_id = dashboard_client

    resp = client.post(
        "/api/repos/acme/dash-app/blocked-authors",
        json={"author_login": "atacante", "reason": "backdoor en PR #12"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["author_login"] == "atacante"

    resp = client.get("/api/repos/acme/dash-app/blocked-authors")
    assert resp.status_code == 200
    logins = [b["author_login"] for b in resp.json()]
    assert logins == ["atacante"]

    resp = client.post(
        "/api/repos/acme/dash-app/blocked-authors",
        json={"author_login": "atacante", "reason": "otra vez"},
    )
    assert resp.status_code == 409

    resp = client.delete("/api/repos/acme/dash-app/blocked-authors/atacante")
    assert resp.status_code == 200

    resp = client.get("/api/repos/acme/dash-app/blocked-authors")
    assert resp.json() == []
