"""Tests de rate limiting en watchgate/dashboard/backend/auth.py::password_login.

Caso real encontrado en revisión: no había ningún límite de intentos en
`/api/auth/login` -- fuerza bruta sin bloqueo de cuenta, sin backoff,
combinado con un canal lateral de tiempo (ya arreglado aparte) que permitía
enumerar logins válidos.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from watchgate.dashboard.backend import auth as auth_module
from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    auth_module._LOGIN_ATTEMPTS.clear()
    yield
    auth_module._LOGIN_ATTEMPTS.clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(db_path))
    with database.db_session(db_path) as conn:
        database.init_db(conn)
        database.upsert_user(conn, "bob", "correct-password", "Bob")
    return TestClient(app)


def test_password_login_blocks_after_max_failed_attempts(client: TestClient) -> None:
    for _ in range(auth_module._LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        resp = client.post("/api/auth/login", json={"username": "bob", "password": "wrong"})
        assert resp.status_code == 401

    blocked = client.post("/api/auth/login", json={"username": "bob", "password": "wrong"})
    assert blocked.status_code == 429

    # Ni siquiera con la contraseña CORRECTA se cuela mientras dure el bloqueo.
    still_blocked = client.post(
        "/api/auth/login", json={"username": "bob", "password": "correct-password"}
    )
    assert still_blocked.status_code == 429


def test_password_login_does_not_rate_limit_other_usernames(client: TestClient) -> None:
    for _ in range(auth_module._LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        client.post("/api/auth/login", json={"username": "bob", "password": "wrong"})

    other = client.post("/api/auth/login", json={"username": "carol", "password": "wrong"})
    assert other.status_code == 401  # no 429 -- el límite es por usuario


def test_successful_login_clears_previous_failed_attempts(client: TestClient) -> None:
    for _ in range(auth_module._LOGIN_RATE_LIMIT_MAX_ATTEMPTS - 1):
        client.post("/api/auth/login", json={"username": "bob", "password": "wrong"})

    ok = client.post("/api/auth/login", json={"username": "bob", "password": "correct-password"})
    assert ok.status_code == 200

    # El contador se reseteó -- un fallo posterior no hereda los intentos previos.
    resp = client.post("/api/auth/login", json={"username": "bob", "password": "wrong"})
    assert resp.status_code == 401
