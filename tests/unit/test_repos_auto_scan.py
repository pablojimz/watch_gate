"""Tests unitarios para la monitorización automática y periódica de PRs externas."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session

# Configurar Fernet key para cifrado de campos de DB en tests
os.environ["WATCHGATE_DB_SECRET"] = "1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I="
import watchgate.db.crypto

watchgate.db.crypto._fernet = Fernet("1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=")

from watchgate.adapters.github_client import GitHubClient  # noqa: E402
from watchgate.dashboard.backend.main import app  # noqa: E402
from watchgate.db.connection import build_engine, get_db_session  # noqa: E402
from watchgate.db.models import MonitoredRepo, VCSConnection  # noqa: E402
from watchgate.db.repository import create_organization  # noqa: E402
from watchgate.service.repo_polling import RepoPollingService  # noqa: E402


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_auto_scan.db"
    test_engine = build_engine(f"sqlite:///{db_file}")

    from watchgate.db.connection import SQLModel

    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        yield session


def test_github_client_list_pull_requests_with_etag_200():
    client = GitHubClient("fake_token")
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [{"number": 1, "title": "Test PR"}]
    mock_response.headers = {"ETag": '"etag_123"'}

    with patch.object(client, "_request", return_value=mock_response):
        prs, etag = client.list_recent_pull_requests_with_etag("owner", "repo", etag='"etag_000"')
        assert prs == [{"number": 1, "title": "Test PR"}]
        assert etag == '"etag_123"'


def test_github_client_list_pull_requests_with_etag_304():
    client = GitHubClient("fake_token")
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 304

    with patch.object(client, "_request", return_value=mock_response):
        prs, etag = client.list_recent_pull_requests_with_etag("owner", "repo", etag='"etag_123"')
        assert prs is None
        assert etag == '"etag_123"'


def test_repo_polling_service_get_candidate_repos(test_db_session):
    with patch("watchgate.service.repo_polling.get_session", return_value=iter([test_db_session])):
        org = create_organization(test_db_session, "Org AutoScan")
        vcs = VCSConnection(id="vcs-1", org_id=org.id, access_token="token_vcs")
        test_db_session.add(vcs)

        repo1 = MonitoredRepo(
            id="repo-1",
            org_id=org.id,
            vcs_connection_id=vcs.id,
            repo_path="owner/repo1",
            monitor_type="audited",
            status="active",
            auto_scan_prs=True,
            scan_interval_minutes=15,
        )
        repo_managed = MonitoredRepo(
            id="repo-2",
            org_id=org.id,
            repo_path="owner/repo2",
            monitor_type="managed",
            status="active",
            auto_scan_prs=True,
        )
        repo_no_token = MonitoredRepo(
            id="repo-3",
            org_id=org.id,
            repo_path="owner/repo3",
            monitor_type="audited",
            status="active",
            auto_scan_prs=True,
        )
        test_db_session.add_all([repo1, repo_managed, repo_no_token])
        test_db_session.commit()

        with patch.dict(os.environ, {}, clear=True):
            candidates = RepoPollingService.get_candidate_repos()
            assert len(candidates) == 3
            assert candidates[0]["repo_path"] == "owner/repo1"
            assert candidates[0]["token"] == "token_vcs"


def test_repo_polling_service_get_candidate_repos_ignore_interval(test_db_session):
    from datetime import UTC, datetime

    sess_target = "watchgate.service.repo_polling.get_session"
    with patch(sess_target, side_effect=lambda: iter([test_db_session])):
        org = create_organization(test_db_session, "Org AutoScan Ignore")
        repo = MonitoredRepo(
            id="repo-recent",
            org_id=org.id,
            repo_path="owner/recentrepo",
            status="active",
            auto_scan_prs=True,
            scan_interval_minutes=60,
            last_polled_at=datetime.now(UTC),
        )
        test_db_session.add(repo)
        test_db_session.commit()

        normal_candidates = RepoPollingService.get_candidate_repos(ignore_interval=False)
        assert len(normal_candidates) == 0

        ignored_candidates = RepoPollingService.get_candidate_repos(ignore_interval=True)
        assert len(ignored_candidates) == 1
        assert ignored_candidates[0]["repo_path"] == "owner/recentrepo"


def test_repo_polling_service_poll_all_candidates_enqueues_and_handles_errors(test_db_session):
    org = create_organization(test_db_session, "Org AutoScan 2")
    vcs = VCSConnection(id="vcs-2", org_id=org.id, access_token="token_vcs2")
    test_db_session.add(vcs)

    repo = MonitoredRepo(
        id="repo-scan-1",
        org_id=org.id,
        vcs_connection_id=vcs.id,
        repo_path="owner/scanrepo",
        monitor_type="audited",
        status="active",
        auto_scan_prs=True,
        scan_interval_minutes=15,
    )
    test_db_session.add(repo)
    test_db_session.commit()

    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = None

    target_prs = "watchgate.adapters.github_client.GitHubClient.list_all_open_pull_requests"
    target_sess = "watchgate.service.repo_polling.get_session"
    with (
        patch(target_sess, side_effect=lambda: iter([test_db_session])),
        patch("watchgate.dashboard.backend.tasks.get_queue", return_value=mock_queue),
        patch(target_prs) as mock_fetch,
    ):
        mock_fetch.return_value = [{"number": 101}, {"number": 102}]
        enqueued = RepoPollingService.poll_all_candidates()

        assert enqueued == 2
        assert mock_queue.enqueue.call_count == 2

        # Probamos cuando ocurre un error continuo
        mock_fetch.side_effect = Exception("GitHub API Down")
        for _ in range(5):
            repo_to_reset = test_db_session.get(MonitoredRepo, "repo-scan-1")
            if repo_to_reset:
                repo_to_reset.last_polled_at = None
                test_db_session.commit()
            RepoPollingService.poll_all_candidates()

        repo_updated = test_db_session.get(MonitoredRepo, "repo-scan-1")
        assert repo_updated.status == "error"
        assert repo_updated.consecutive_errors >= 5


def test_patch_external_repo_endpoint_and_rbac(test_db_session):
    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user

    user_admin = _get_or_create_db_user(test_db_session, "admin@corp.com")
    user_revisor = _get_or_create_db_user(test_db_session, "revisor@corp.com")
    user_revisor.org_id = user_admin.org_id
    test_db_session.add(user_revisor)
    test_db_session.commit()

    repo = MonitoredRepo(
        id="repo-patch-1",
        org_id=user_admin.org_id,
        repo_path="acme/patchrepo",
        monitor_type="audited",
        status="active",
        auto_scan_prs=True,
        scan_interval_minutes=30,
    )
    test_db_session.add(repo)
    test_db_session.commit()

    # Configurar sesión en la BD del dashboard para require_role
    from watchgate.dashboard.backend.db import db_session as dash_db_session
    from watchgate.dashboard.backend.db import upsert_role

    with dash_db_session() as dash_conn:
        upsert_role(dash_conn, "admin@corp.com", "acme/patchrepo", "admin_organizacion")
        upsert_role(dash_conn, "revisor@corp.com", "acme/patchrepo", "revisor")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token_admin = create_session_token("admin@corp.com")
    token_revisor = create_session_token("revisor@corp.com")

    # 1. Usuario revisor intenta actualizar -> 403 Forbidden
    client.cookies.set("watchgate_session", token_revisor)
    response = client.patch("/api/repos/external/repo-patch-1", json={"scan_interval_minutes": 15})
    assert response.status_code == 403

    # 2. Usuario admin actualiza con intervalo demasiado bajo (< 5 min) -> 400 Bad Request
    client.cookies.set("watchgate_session", token_admin)
    response = client.patch("/api/repos/external/repo-patch-1", json={"scan_interval_minutes": 2})
    assert response.status_code == 400

    # 3. Usuario admin actualiza correctamente
    response = client.patch(
        "/api/repos/external/repo-patch-1",
        json={"auto_scan_prs": False, "scan_interval_minutes": 60, "status": "paused"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["auto_scan_prs"] is False
    assert data["scan_interval_minutes"] == 60
    assert data["status"] == "paused"

    app.dependency_overrides.clear()


def test_add_external_repo_triggers_instant_poll(test_db_session):
    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user

    _get_or_create_db_user(test_db_session, "creator@corp.com")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator@corp.com")
    client.cookies.set("watchgate_session", token)

    target_poll = "watchgate.service.repo_polling.RepoPollingService.poll_repo_by_id"
    with patch(target_poll) as mock_poll:
        response = client.post(
            "/api/repos/external",
            json={"repo_path": "openclaw/instantrepo", "monitor_type": "audited"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["repo_path"] == "openclaw/instantrepo"
        assert mock_poll.called
        assert mock_poll.call_args[0][0] == data["id"]
        assert mock_poll.call_args[1].get("ignore_interval") is True

    app.dependency_overrides.clear()
