"""Tests del endpoint de reclamación de instalaciones de la GitHub App
(POST /api/repos/external/installations/claim -- routers/repos.py).

Era el eslabón que faltaba del modo managed: el webhook de PRs resuelve la
organización buscando una VCSConnection por installation_id, pero nada
creaba esa fila -- instalar la App no tenía ningún efecto.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

os.environ["WATCHGATE_DB_SECRET"] = "1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I="
import watchgate.db.crypto

watchgate.db.crypto._fernet = Fernet("1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=")

from watchgate.adapters import github_app  # noqa: E402
from watchgate.dashboard.backend.auth import get_current_user  # noqa: E402
from watchgate.dashboard.backend.main import app  # noqa: E402
from watchgate.dashboard.backend.schemas import User as DashboardUser  # noqa: E402
from watchgate.db.connection import get_db_session  # noqa: E402
from watchgate.db.models import MonitoredRepo, VCSConnection  # noqa: E402
from watchgate.db.repository import create_organization  # noqa: E402


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_claim.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def dashboard_client(test_db_session):
    mock_user = DashboardUser(login="javier_dev")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: test_db_session
    client = TestClient(app)
    yield client, test_db_session
    app.dependency_overrides.clear()


def _claim(client: TestClient, installation_id: str):
    return client.post(
        "/api/repos/external/installations/claim",
        json={"installation_id": installation_id},
    )


def test_claim_creates_connection_and_managed_repos(
    dashboard_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, session = dashboard_client
    monkeypatch.setattr(github_app, "github_app_configured", lambda: True)
    monkeypatch.setattr(
        github_app,
        "list_installation_repositories",
        lambda installation_id: ["acme/uno", "acme/dos"],
    )

    response = _claim(client, "424242")
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["installation_id"] == "424242"
    assert data["app_configured"] is True
    assert {r["repo_path"] for r in data["repos"]} == {"acme/uno", "acme/dos"}
    assert all(r["monitor_type"] == "managed" for r in data["repos"])

    vcs = session.exec(
        select(VCSConnection).where(VCSConnection.installation_id == "424242")
    ).first()
    assert vcs is not None
    repos = session.exec(select(MonitoredRepo)).all()
    assert {r.repo_path for r in repos} == {"acme/uno", "acme/dos"}
    assert all(r.vcs_connection_id == vcs.id for r in repos)


def test_claim_is_idempotent_for_the_same_org(
    dashboard_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, session = dashboard_client
    monkeypatch.setattr(github_app, "github_app_configured", lambda: True)
    monkeypatch.setattr(
        github_app, "list_installation_repositories", lambda installation_id: ["acme/uno"]
    )

    first = _claim(client, "424242")
    second = _claim(client, "424242")
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["vcs_connection_id"] == second.json()["vcs_connection_id"]
    assert len(session.exec(select(MonitoredRepo)).all()) == 1
    assert len(session.exec(select(VCSConnection)).all()) == 1


def test_claim_conflicts_when_another_org_owns_the_installation(
    dashboard_client,
) -> None:
    client, session = dashboard_client
    other_org = create_organization(session, name="Otra Org")
    session.add(
        VCSConnection(id="vcs-ajena", org_id=other_org.id, installation_id="424242")
    )
    session.commit()

    response = _claim(client, "424242")
    assert response.status_code == 409


def test_claim_rejects_non_numeric_installation_id(dashboard_client) -> None:
    client, _session = dashboard_client
    response = _claim(client, "abc; rm -rf /")
    assert response.status_code == 400


def test_github_app_info_announces_install_url_from_slug(
    dashboard_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _session = dashboard_client
    monkeypatch.setenv("WATCHGATE_GITHUB_APP_SLUG", "watchgate")
    monkeypatch.setattr(github_app, "github_app_configured", lambda: True)

    response = client.get("/api/repos/external/github-app")
    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "install_url": "https://github.com/apps/watchgate/installations/new",
    }


def test_github_app_info_without_slug_returns_null_url(
    dashboard_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _session = dashboard_client
    monkeypatch.delenv("WATCHGATE_GITHUB_APP_SLUG", raising=False)
    monkeypatch.setattr(github_app, "github_app_configured", lambda: False)

    response = client.get("/api/repos/external/github-app")
    assert response.status_code == 200
    assert response.json() == {"configured": False, "install_url": None}


def test_claim_without_app_credentials_still_creates_the_connection(
    dashboard_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin WATCHGATE_GITHUB_APP_ID/clave en el servidor no se pueden listar
    los repos de la instalación, pero la conexión org<->installation_id SÍ
    debe quedar registrada -- es lo que hace que los webhooks de PR
    encuentren la organización; los repos se añaden a mano después."""
    client, session = dashboard_client
    monkeypatch.setattr(github_app, "github_app_configured", lambda: False)

    response = _claim(client, "777")
    assert response.status_code == 201
    data = response.json()
    assert data["app_configured"] is False
    assert data["repos"] == []
    assert (
        session.exec(select(VCSConnection).where(VCSConnection.installation_id == "777")).first()
        is not None
    )
