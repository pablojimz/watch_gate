"""Tests unitarios para el alta de repos de servidor Git propio desde el
Dashboard (POST /api/repos/external/git-server) -- crea el MonitoredRepo
(monitor_type="git_server") y una API key atada a él en un solo paso, antes
de que el repo tenga ningún push analizado. Ver docs/manual_git_hooks.md §6.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.main import app
from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user, get_db_session
from watchgate.dashboard.backend.schemas import User as DashboardUser
from watchgate.db.models import MonitoredRepo, UserAPIKey
from watchgate.db.repository import create_organization


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_git_server_repo.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def dashboard_client(test_db_session):
    mock_user = DashboardUser(login="server_admin")

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    client = TestClient(app)
    yield client, test_db_session

    app.dependency_overrides.clear()


def test_connect_git_server_repo_creates_repo_and_bound_key(dashboard_client):
    client, session = dashboard_client

    response = client.post(
        "/api/repos/external/git-server", json={"repo_path": "demo/repo-prueba"}
    )
    assert response.status_code == 201
    data = response.json()

    assert data["repo"]["repo_path"] == "demo/repo-prueba"
    assert data["repo"]["monitor_type"] == "git_server"
    assert data["repo"]["status"] == "active"
    assert data["api_key"].startswith("wg_live_")
    assert data["key_prefix"].startswith("wg_live_")
    assert data["hook_download_url"].endswith("/api/v1/hooks/pre-receive")
    assert data["hook_download_url"].startswith(data["engine_api_url"])

    db_user = _get_or_create_db_user(session, "server_admin")
    repo = session.exec(
        select(MonitoredRepo).where(
            MonitoredRepo.org_id == db_user.org_id, MonitoredRepo.repo_path == "demo/repo-prueba"
        )
    ).first()
    assert repo is not None

    key = session.exec(
        select(UserAPIKey).where(UserAPIKey.monitored_repo_id == repo.id)
    ).first()
    assert key is not None
    assert key.name == "Hook servidor Git: demo/repo-prueba"


def test_connect_git_server_repo_rejects_duplicate(dashboard_client):
    client, session = dashboard_client

    db_user = _get_or_create_db_user(session, "server_admin")
    session.add(
        MonitoredRepo(
            id="existing-repo",
            org_id=db_user.org_id,
            repo_path="demo/ya-conectado",
            monitor_type="git_server",
        )
    )
    session.commit()

    response = client.post(
        "/api/repos/external/git-server", json={"repo_path": "demo/ya-conectado"}
    )
    assert response.status_code == 409


def test_connect_git_server_repo_strips_slashes(dashboard_client):
    client, _session = dashboard_client

    response = client.post(
        "/api/repos/external/git-server", json={"repo_path": "/demo/con-barras/"}
    )
    assert response.status_code == 201
    assert response.json()["repo"]["repo_path"] == "demo/con-barras"


def test_connect_git_server_repo_isolates_orgs(dashboard_client):
    """Un repo con el mismo repo_path en OTRA organización no debe chocar
    con el 409 de duplicado -- la unicidad es por (org_id, repo_path)."""
    client, session = dashboard_client

    other_org = create_organization(session, name="Otra Org")
    session.add(
        MonitoredRepo(
            id="repo-otra-org",
            org_id=other_org.id,
            repo_path="demo/compartido",
            monitor_type="git_server",
        )
    )
    session.commit()

    response = client.post("/api/repos/external/git-server", json={"repo_path": "demo/compartido"})
    assert response.status_code == 201
