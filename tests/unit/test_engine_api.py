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
from watchgate.db.repository import create_api_key, create_user


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_api.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine


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
    user = create_user(session, email="dev@watchgate.io", name="Dev User")
    _, raw_token = create_api_key(session, user_id=user.id, name="Test Key")

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
