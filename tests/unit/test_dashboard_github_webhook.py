"""Tests de watchgate/dashboard/backend/routers/webhooks.py::github_webhook.

Router aislado (no depende de la BD del dashboard ni de auth), así que se
monta en una app mínima en vez de levantar `create_app()` completo -- más
rápido y sin necesitar Postgres/SQLite de por medio.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from watchgate.dashboard.backend.routers import webhooks as webhooks_module

_SECRET = "test-github-webhook-secret"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(webhooks_module, "_WEBHOOK_SECRET", _SECRET)
    app = FastAPI()
    app.include_router(webhooks_module.router, prefix="/api")
    return TestClient(app)


def _sign(body: bytes) -> str:
    digest = hmac.new(_SECRET.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _post(client: TestClient, payload: dict, event: str = "pull_request"):
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": event,
            "Content-Type": "application/json",
        },
    )


def test_pull_request_opened_enqueues_the_managed_scan_without_blocking_the_event_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresión: `queue.enqueue()` es una llamada bloqueante de red
    (redis-py estándar), y este endpoint es `async def` -- sin
    `run_in_threadpool` esa llamada bloquearía el event loop entero
    mientras Redis responde. Aquí solo se comprueba el resultado (se
    encola con los argumentos correctos y responde 202), no el mecanismo
    interno -- pero corre sobre la implementación real con
    `run_in_threadpool`, no una versión simplificada."""
    calls = []

    class _FakeQueue:
        def enqueue(self, *args):
            calls.append(args)

    monkeypatch.setattr(webhooks_module, "get_queue", lambda: _FakeQueue())

    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {"number": 42},
        "installation": {"id": 999},
    }
    response = _post(client, payload)

    assert response.status_code == 202
    assert calls == [
        ("watchgate.dashboard.backend.tasks.run_managed_scan", "acme/widgets", 42, "999")
    ]


def test_non_pull_request_event_is_ignored_without_enqueueing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "get_queue",
        lambda: (_ for _ in ()).throw(AssertionError("no debería encolarse")),
    )
    response = _post(client, {"action": "opened"}, event="issue_comment")
    assert response.status_code == 200


def test_missing_installation_id_is_ignored_without_enqueueing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "get_queue",
        lambda: (_ for _ in ()).throw(AssertionError("no debería encolarse")),
    )
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {"number": 42},
    }
    response = _post(client, payload)
    assert response.status_code == 200


def test_invalid_signature_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/webhooks/github",
        json={"action": "opened"},
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 403
