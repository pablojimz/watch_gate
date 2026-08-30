"""Tests de watchgate/dashboard/backend/tasks.py::repo_is_authorized -- el
sistema real de "solo repos suscritos/autorizados se analizan" (ver
routers/webhooks.py, que lo usa para rechazar con 403 antes de encolar
nada, y run_managed_scan, que lo repite como defensa en profundidad).

Antes de esto, `run_managed_scan` solo comprobaba que `installation_id`
estuviera reclamado por una organización (`VCSConnection`) -- nunca que
`repo_path` fuera un `MonitoredRepo` activo de esa organización. Cualquier
repo al que la GitHub App tuviera acceso se analizaba igual, y pausar un
repo desde el dashboard no tenía ningún efecto en este camino."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session

os.environ["WATCHGATE_DB_SECRET"] = "1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I="
import watchgate.db.crypto  # noqa: E402

watchgate.db.crypto._fernet = Fernet("1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=")

from watchgate.dashboard.backend import tasks  # noqa: E402
from watchgate.db.connection import build_engine  # noqa: E402
from watchgate.db.models import MonitoredRepo, VCSConnection  # noqa: E402
from watchgate.db.repository import create_organization  # noqa: E402


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_repo_authorization.db"
    test_engine = build_engine(f"sqlite:///{db_file}")

    from watchgate.db.connection import SQLModel

    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        yield session


def _patched_session(test_db_session):
    return patch(
        "watchgate.dashboard.backend.tasks.get_session",
        side_effect=lambda: iter([test_db_session]),
    )


def test_authorized_when_active_monitored_repo_exists(test_db_session):
    org = create_organization(test_db_session, "Org OK")
    vcs = VCSConnection(id="vcs-1", org_id=org.id, installation_id="inst-ok")
    test_db_session.add(vcs)
    test_db_session.add(
        MonitoredRepo(
            id="repo-1",
            org_id=org.id,
            vcs_connection_id=vcs.id,
            repo_path="acme/widgets",
            monitor_type="managed",
            status="active",
        )
    )
    test_db_session.commit()

    with _patched_session(test_db_session):
        authorized, reason = tasks.repo_is_authorized("inst-ok", "acme/widgets")
    assert authorized is True
    assert reason == ""


def test_unauthorized_when_installation_never_claimed(test_db_session):
    with _patched_session(test_db_session):
        authorized, reason = tasks.repo_is_authorized("inst-nunca-reclamada", "acme/widgets")
    assert authorized is False
    assert "no reclamado" in reason


def test_unauthorized_when_repo_not_registered_for_that_org(test_db_session):
    """La instalación existe y está reclamada, pero ESE repo en concreto no
    se dio de alta como MonitoredRepo -- p. ej. un repo fuera del alcance
    real que alguien intenta colar con un installation_id válido."""
    org = create_organization(test_db_session, "Org Sin Ese Repo")
    vcs = VCSConnection(id="vcs-2", org_id=org.id, installation_id="inst-sin-repo")
    test_db_session.add(vcs)
    test_db_session.commit()

    with _patched_session(test_db_session):
        authorized, reason = tasks.repo_is_authorized("inst-sin-repo", "acme/no-registrado")
    assert authorized is False
    assert "no dado de alta" in reason


def test_unauthorized_when_repo_is_paused(test_db_session):
    """Pausar un repo desde el dashboard SÍ debe tener efecto real -- este
    es justo el bug que se arregla: antes, un repo pausado se seguía
    analizando igual en cada PR."""
    org = create_organization(test_db_session, "Org Pausada")
    vcs = VCSConnection(id="vcs-3", org_id=org.id, installation_id="inst-paused")
    test_db_session.add(vcs)
    test_db_session.add(
        MonitoredRepo(
            id="repo-3",
            org_id=org.id,
            vcs_connection_id=vcs.id,
            repo_path="acme/pausado",
            monitor_type="managed",
            status="paused",
        )
    )
    test_db_session.commit()

    with _patched_session(test_db_session):
        authorized, reason = tasks.repo_is_authorized("inst-paused", "acme/pausado")
    assert authorized is False
    assert "paused" in reason


def test_run_managed_scan_returns_early_without_calling_github_when_unauthorized(
    test_db_session,
):
    """El propio `run_managed_scan` rechaza igual (defensa en profundidad):
    ni siquiera debe llegar a instanciar `GitHubClient` para un repo no
    autorizado -- nada de gastar cuota ni tráfico de red."""
    org = create_organization(test_db_session, "Org Managed Unauthorized")
    vcs = VCSConnection(id="vcs-4", org_id=org.id, installation_id="inst-4")
    test_db_session.add(vcs)
    # A propósito: NO se crea ningún MonitoredRepo para "acme/fuera-de-alcance".
    test_db_session.commit()

    with (
        _patched_session(test_db_session),
        patch("watchgate.dashboard.backend.tasks.GitHubClient") as MockClient,
    ):
        tasks.run_managed_scan("acme/fuera-de-alcance", 1, "inst-4")

    MockClient.assert_not_called()
