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


@pytest.fixture(autouse=True)
def _authorized_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """repo_is_authorized() consulta la BD real (Engine DB) -- este fichero
    de tests monta el router aislado a propósito (ver docstring del
    módulo), así que por defecto se mockea a "autorizado" para que los
    tests existentes (que no prueban esta comprobación) no necesiten una
    BD real. Los tests de rechazo de más abajo la sobreescriben."""
    monkeypatch.setattr(webhooks_module, "repo_is_authorized", lambda *a, **k: (True, ""))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # El secreto se lee del entorno POR PETICIÓN (no en import), así que se
    # monkeypatchea la variable, no un atributo del módulo.
    monkeypatch.setenv("WATCHGATE_GITHUB_WEBHOOK_SECRET", _SECRET)
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


def test_missing_secret_fails_closed_with_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regresión (fallo de seguridad real): sin la variable de entorno, la
    firma se verificaba con clave VACÍA -- cualquiera podía calcular ese
    HMAC y encolar escaneos falsos. Ahora la ausencia del secreto es un
    error de configuración del servidor (503), fail-closed, igual que el
    endpoint equivalente de la Engine API."""
    monkeypatch.delenv("WATCHGATE_GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    app = FastAPI()
    app.include_router(webhooks_module.router, prefix="/api")
    no_secret_client = TestClient(app)

    body = json.dumps({"action": "opened"}).encode("utf-8")
    empty_key_signature = "sha256=" + hmac.new(b"", msg=body, digestmod=hashlib.sha256).hexdigest()
    response = no_secret_client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": empty_key_signature,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 503


def test_unauthorized_repo_is_rejected_with_403_and_never_enqueued(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El rechazo real de "repos no autorizados/suscritos" -- sin esto,
    cualquier repo al que la GitHub App tuviera acceso se analizaba igual
    (bug real, ver docstring de repo_is_authorized en tasks.py)."""
    monkeypatch.setattr(
        webhooks_module,
        "repo_is_authorized",
        lambda installation_id, repo_path: (False, "repo en estado 'paused', no 'active'"),
    )
    monkeypatch.setattr(
        webhooks_module,
        "get_queue",
        lambda: (_ for _ in ()).throw(AssertionError("no debería encolarse")),
    )
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/no-autorizado"},
        "pull_request": {"number": 42},
        "installation": {"id": 999},
    }
    response = _post(client, payload)
    assert response.status_code == 403


def test_authorized_repo_reaches_the_queue_with_the_right_args(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Complementa el test de arriba: comprueba que repo_is_authorized()
    recibe exactamente installation_id y repo_path del payload, no algún
    otro valor por accidente (p. ej. intercambiados)."""
    seen_args = []

    def _fake_authorized(installation_id: str, repo_path: str) -> tuple[bool, str]:
        seen_args.append((installation_id, repo_path))
        return True, ""

    monkeypatch.setattr(webhooks_module, "repo_is_authorized", _fake_authorized)

    calls = []

    class _FakeQueue:
        def enqueue(self, *args):
            calls.append(args)

    monkeypatch.setattr(webhooks_module, "get_queue", lambda: _FakeQueue())

    payload = {
        "action": "synchronize",
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {"number": 7},
        "installation": {"id": 999},
    }
    response = _post(client, payload)

    assert response.status_code == 202
    assert seen_args == [("999", "acme/widgets")]
    assert calls == [
        ("watchgate.dashboard.backend.tasks.run_managed_scan", "acme/widgets", 7, "999")
    ]


def test_malformed_payload_with_valid_signature_returns_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un payload firmado pero sin repository.full_name / pull_request.number
    (p. ej. un redelivery editado a mano) debe dar 400, no un 500 por
    KeyError."""
    monkeypatch.setattr(
        webhooks_module,
        "get_queue",
        lambda: (_ for _ in ()).throw(AssertionError("no debería encolarse")),
    )
    payload = {"action": "opened", "installation": {"id": 999}}
    response = _post(client, payload)
    assert response.status_code == 400
