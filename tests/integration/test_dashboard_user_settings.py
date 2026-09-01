"""Integration tests for /api/settings/user and RBAC isolation, Fernet encryption, and SSRF."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine

os.environ["WATCHGATE_DASHBOARD_DB"] = str(Path(__file__).resolve().parent / "_dashboard_test.db")
os.environ["WATCHGATE_DASHBOARD_DEV_MODE"] = "1"
os.environ["WATCHGATE_DASHBOARD_SEED"] = "0"
os.environ["WATCHGATE_DASHBOARD_SECRET"] = "test-secret"
os.environ["WATCHGATE_DB_SECRET"] = "gP7Q3Z8k1Y2x4N5v6W7e8R9t0Y1u2I3o4P5a6S7d8F9="

import watchgate.db.connection as db_connection  # noqa: E402
from watchgate.dashboard.backend import db as database  # noqa: E402
from watchgate.dashboard.backend.main import create_app  # noqa: E402
from watchgate.dashboard.backend.models import DashboardUser  # noqa: E402


def _isolate_db_connection_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    fresh_engine = create_engine(
        f"sqlite:///{tmp_path / 'app.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db_connection, "default_engine", fresh_engine)
    return fresh_engine


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    _isolate_db_connection_engine(monkeypatch, tmp_path)
    db_path = tmp_path / "dashboard.db"
    os.environ["WATCHGATE_DASHBOARD_DB"] = str(db_path)

    with database.db_session(db_path) as conn:
        database.init_db(conn)
        database.upsert_user(conn, "admin", "Admin123", "Admin User")
        database.upsert_user(conn, "reviewer", "review123", "Revisor User")

        database.upsert_role(conn, "admin", "acme/payments-api", "mantenedor")
        database.upsert_role(conn, "reviewer", "acme/payments-api", "revisor")

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_user_settings_get_and_put(client: TestClient, tmp_path: Path):
    # Login as reviewer
    login_resp = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert login_resp.status_code == 200

    # GET /api/settings/user
    resp = client.get("/api/settings/user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == "reviewer"
    assert data["display_name"] == "Revisor User"
    assert data["role"] == "revisor"
    assert data["github_token_set"] is False

    # PUT /api/settings/user
    put_resp = client.put(
        "/api/settings/user",
        json={
            "display_name": "Revisor Actualizado",
            "github_api_url": "https://github.mycompany.com/api/v3",
            "github_token": "ghp_1234567890abcdef",
        },
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["display_name"] == "Revisor Actualizado"
    assert updated["github_api_url"] == "https://github.mycompany.com/api/v3"
    assert updated["github_token_set"] is True
    assert updated["github_token_masked"] is not None
    assert "ghp_" in updated["github_token_masked"]
    assert "1234567890abcdef" not in updated["github_token_masked"]  # Token is masked

    # Condition 1: Verify Fernet encryption in DB
    db_path = tmp_path / "dashboard.db"
    with database.db_session(db_path) as conn:
        user_row = conn.get(DashboardUser, "reviewer")
        assert user_row is not None
        # In memory/ORM, decrypted automatically via EncryptedString
        assert user_row.github_token == "ghp_1234567890abcdef"


def test_user_settings_includes_per_repo_role_breakdown(client: TestClient):
    """`repo_roles` (nuevo) es el desglose completo por repo -- distinto de
    `role`, que ya existía y es solo el más alto agregado. Ver
    db.py::list_roles_for_user."""
    login_resp = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert login_resp.status_code == 200

    resp = client.get("/api/settings/user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_roles"] == [{"repo": "acme/payments-api", "role": "revisor"}]


def test_change_own_password_requires_correct_current_password(client: TestClient):
    login_resp = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert login_resp.status_code == 200

    # Contraseña actual incorrecta -> 401, no cambia nada.
    wrong = client.put(
        "/api/settings/user/password",
        json={"current_password": "not-the-real-password", "new_password": "nuevaClave123"},
    )
    assert wrong.status_code == 401

    # Sigue pudiendo entrar con la contraseña de siempre.
    still_works = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert still_works.status_code == 200

    # Contraseña nueva demasiado corta -> 422 (validación de schema).
    weak = client.put(
        "/api/settings/user/password",
        json={"current_password": "review123", "new_password": "corta"},
    )
    assert weak.status_code == 422


def test_change_own_password_success_updates_login_credentials(client: TestClient):
    login_resp = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert login_resp.status_code == 200

    changed = client.put(
        "/api/settings/user/password",
        json={"current_password": "review123", "new_password": "nuevaClaveSegura456"},
    )
    assert changed.status_code == 204

    # La contraseña vieja ya no sirve para entrar de nuevo.
    old_login = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert old_login.status_code == 401

    # La nueva sí.
    new_login = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "nuevaClaveSegura456"}
    )
    assert new_login.status_code == 200


def test_user_settings_rbac_isolation(client: TestClient):
    """Condition 4: User 'reviewer' can update profile, forbidden from /settings/llm or /ui."""
    login_resp = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert login_resp.status_code == 200

    # User can edit their own settings
    user_put = client.put("/api/settings/user", json={"display_name": "Revisor Ok"})
    assert user_put.status_code == 200

    # User is forbidden from editing LLM org settings
    llm_put = client.put("/api/settings/llm", json={"provider": "anthropic", "model": "claude-3"})
    assert llm_put.status_code == 403

    # User is forbidden from editing global UI settings
    ui_put = client.put("/api/settings/ui", json={"primary_color": "#000000"})
    assert ui_put.status_code == 403


def test_ssrf_protection_in_production_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Condition 2: Rejects private/local IP addresses in production mode."""
    login_resp = client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "review123"}
    )
    assert login_resp.status_code == 200

    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")

    bad_urls = [
        "http://169.254.169.254/latest/meta-data",
        "http://localhost:8000/api",
        "http://127.0.0.1:6379",
        "http://10.0.0.1/api",
    ]

    for bad_url in bad_urls:
        resp = client.put("/api/settings/user", json={"github_api_url": bad_url})
        assert resp.status_code in (
            400,
            422,
        ), f"Expected 400/422 for {bad_url}, got {resp.status_code}"
