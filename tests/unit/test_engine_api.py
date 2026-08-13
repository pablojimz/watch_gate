"""Tests unitarios e integrados para la Engine API de WatchGate (watchgate/api/)."""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from watchgate.api.dependencies import get_db_session
from watchgate.api.main import CryptographicLogFilter, app
from watchgate.db.models import MonitoredRepo
from watchgate.db.repository import create_api_key, create_organization, create_user


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_api.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine
    engine.dispose()


@pytest.fixture
def api_client(test_db_session):
    session, _engine = test_db_session

    app.dependency_overrides[get_db_session] = lambda: session
    client = TestClient(app)
    yield client, session
    app.dependency_overrides.clear()


def test_health_check(api_client):
    client, _ = api_client
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "WatchGate Engine API"}


def test_analyze_unauthorized(api_client):
    client, _ = api_client
    response = client.post("/api/v1/analyze", json={"diff_text": "diff --git a/file.py b/file.py"})
    assert response.status_code == 401


def test_analyze_invalid_key(api_client):
    client, _ = api_client
    headers = {"Authorization": "Bearer wg_live_invalidkey12345678901234567890123456789012"}
    response = client.post(
        "/api/v1/analyze",
        headers=headers,
        json={"diff_text": "diff --git a/file.py b/file.py"},
    )
    assert response.status_code == 401


def test_analyze_success(api_client):
    client, session = api_client
    org = create_organization(session, name="Dev Org")
    user = create_user(session, email="dev@watchgate.io", name="Dev User", org_id=org.id)
    repo = MonitoredRepo(id="repo-acme-backend", org_id=org.id, repo_path="acme/backend")
    session.add(repo)
    session.commit()
    _, raw_token = create_api_key(
        session, user_id=user.id, org_id=org.id, name="Test Key", monitored_repo_id=repo.id
    )

    diff_text = """diff --git a/sample.py b/sample.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/sample.py
@@ -0,0 +1,1 @@
+print("Hello World")
"""

    headers = {"Authorization": f"Bearer {raw_token}"}
    payload = {
        "diff_text": diff_text,
        "base_sha": "abc1234",
        "head_sha": "def5678",
        "metadata": {"pr_id": "42", "repo": "acme/backend"},
    }

    response = client.post("/api/v1/analyze", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "semaforo" in data
    assert data["pr_id"] == "42"
    assert data["repo"] == "acme/backend"


def _diff_text() -> str:
    return """diff --git a/sample.py b/sample.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/sample.py
@@ -0,0 +1,1 @@
+print("Hello World")
"""


def test_analyze_rejects_key_bound_to_a_different_repo(api_client):
    """Puerta 3: una clave nueva (con `monitored_repo_id`) atada al repo A
    no debe poder analizar el repo B, aunque ambos sean de la misma
    organización -- cada clave queda restringida a un único repo."""
    client, session = api_client
    org = create_organization(session, name="Dev Org")
    user = create_user(session, email="dev2@watchgate.io", name="Dev User 2", org_id=org.id)
    repo_a = MonitoredRepo(id="repo-a", org_id=org.id, repo_path="acme/repo-a")
    repo_b = MonitoredRepo(id="repo-b", org_id=org.id, repo_path="acme/repo-b")
    session.add(repo_a)
    session.add(repo_b)
    session.commit()
    _, raw_token = create_api_key(
        session, user_id=user.id, org_id=org.id, name="Key for A", monitored_repo_id=repo_a.id
    )

    headers = {"Authorization": f"Bearer {raw_token}"}
    payload = {
        "diff_text": _diff_text(),
        "metadata": {"pr_id": "1", "repo": "acme/repo-b"},
    }

    response = client.post("/api/v1/analyze", headers=headers, json=payload)
    assert response.status_code == 403
    assert "repo-a" in response.json()["detail"]


def test_analyze_accepts_key_for_its_bound_repo(api_client):
    """Contraparte del test anterior: la misma clave SÍ debe poder analizar
    el repo al que está atada."""
    client, session = api_client
    org = create_organization(session, name="Dev Org")
    user = create_user(session, email="dev3@watchgate.io", name="Dev User 3", org_id=org.id)
    repo_a = MonitoredRepo(id="repo-a2", org_id=org.id, repo_path="acme/repo-a2")
    session.add(repo_a)
    session.commit()
    _, raw_token = create_api_key(
        session, user_id=user.id, org_id=org.id, name="Key for A2", monitored_repo_id=repo_a.id
    )

    headers = {"Authorization": f"Bearer {raw_token}"}
    payload = {
        "diff_text": _diff_text(),
        "metadata": {"pr_id": "2", "repo": "acme/repo-a2"},
    }

    response = client.post("/api/v1/analyze", headers=headers, json=payload)
    assert response.status_code == 200


def test_analyze_legacy_key_without_repo_works_only_for_monitored_repos_of_its_org(api_client):
    """Clave legado (creada antes de este campo, `monitored_repo_id` NULL):
    sigue funcionando como red de seguridad mínima, pero solo para repos ya
    monitorizados por su propia organización -- no para cualquier repo."""
    client, session = api_client
    org = create_organization(session, name="Legacy Org")
    user = create_user(session, email="legacy@watchgate.io", name="Legacy Dev", org_id=org.id)
    monitored = MonitoredRepo(id="repo-legacy", org_id=org.id, repo_path="acme/legacy-repo")
    session.add(monitored)
    session.commit()
    # `monitored_repo_id` explícitamente None -- simula una clave creada
    # antes de este cambio (la API ya no permite crear una nueva así).
    _, raw_token = create_api_key(
        session,
        user_id=user.id,
        org_id=org.id,
        name="Legacy Key",
        monitored_repo_id=None,  # type: ignore[arg-type]
    )

    headers = {"Authorization": f"Bearer {raw_token}"}

    ok_response = client.post(
        "/api/v1/analyze",
        headers=headers,
        json={"diff_text": _diff_text(), "metadata": {"pr_id": "3", "repo": "acme/legacy-repo"}},
    )
    assert ok_response.status_code == 200

    rejected_response = client.post(
        "/api/v1/analyze",
        headers=headers,
        json={"diff_text": _diff_text(), "metadata": {"pr_id": "4", "repo": "acme/not-monitored"}},
    )
    assert rejected_response.status_code == 403


def test_webhook_no_secret_fails_closed(api_client):
    """Antes: sin secreto configurado, el endpoint no verificaba nada y
    aceptaba cualquier payload como legítimo (200). Eso era fail-open --
    cualquiera en internet podía mandar un webhook falso. Ahora la ausencia
    del secreto es en sí misma un error de configuración del servidor
    (503), no una vía libre."""
    client, _ = api_client
    headers = {"X-GitHub-Event": "pull_request"}
    payload = {
        "action": "opened",
        "number": 10,
        "repository": {"full_name": "acme/repo"},
        "pull_request": {"number": 10},
    }

    with patch.dict(os.environ, {}, clear=True):
        response = client.post("/api/v1/webhooks/github", headers=headers, json=payload)
        assert response.status_code == 503


def test_webhook_hmac_verification(api_client):
    client, _ = api_client
    secret = "my_super_secret_webhook_key"

    headers = {
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": "sha256=invalid_signature",
    }
    payload = {"action": "opened"}

    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
        response = client.post("/api/v1/webhooks/github", headers=headers, json=payload)
        assert response.status_code == 401


def test_payload_too_large_middleware(api_client):
    client, _ = api_client
    large_size = 11 * 1024 * 1024  # 11 MB > 10 MB limit
    headers = {"Content-Length": str(large_size)}

    response = client.post("/health", headers=headers)
    assert response.status_code == 413
    assert "10 MB" in response.json()["detail"]


def test_cryptographic_log_filter():
    log_filter = CryptographicLogFilter()

    secret_raw = "wg_live_" + "a" * 64
    anthropic_secret = "sk-ant-api03-" + "b" * 32
    msg = f"User authenticated with key {secret_raw} and key {anthropic_secret}."

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )

    assert log_filter.filter(record)
    assert secret_raw not in record.msg
    assert "sk-ant-" not in record.msg
    assert "[REDACTED_SECRET]" in record.msg
