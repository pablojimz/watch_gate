"""Test de aceptación §13: los 3 roles contra los endpoints de permisos."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# DB aislada por proceso de test.
os.environ["WATCHGATE_DASHBOARD_DB"] = str(Path(__file__).resolve().parent / "_dashboard_test.db")
os.environ["WATCHGATE_DASHBOARD_DEV_MODE"] = "1"
os.environ["WATCHGATE_DASHBOARD_SEED"] = "0"
os.environ["WATCHGATE_DASHBOARD_SECRET"] = "test-secret"


from watchgate.dashboard.backend import db as database  # noqa: E402
from watchgate.dashboard.backend.main import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "dashboard.db"
    os.environ["WATCHGATE_DASHBOARD_DB"] = str(db_path)

    with database.db_session(db_path) as conn:
        database.init_db(conn)
        database.upsert_role(conn, "admin", "acme/payments-api", "admin_organizacion")
        database.upsert_role(conn, "maint", "acme/payments-api", "mantenedor")
        database.upsert_role(conn, "viewer", "acme/payments-api", "revisor")
        # El mantenedor también tiene auth-service; el revisor no.
        database.upsert_role(conn, "maint", "acme/auth-service", "mantenedor")

        from watchgate.core.models import AggregatedResult, LayerResult, Semaforo

        layers = {
            name: LayerResult(layer_name=name, risk_score=10, justification="", skipped=False)
            for name in ("static", "deps", "reputation", "semantic")
        }
        score_id = database.insert_aggregated(
            conn,
            AggregatedResult(
                score=10,
                semaforo=Semaforo.VERDE,
                layer_results=layers,
                weights_used={
                    "static": 0.25,
                    "deps": 0.25,
                    "reputation": 0.15,
                    "semantic": 0.35,
                },
                pr_id="42",
                repo="acme/payments-api",
                timestamp="2026-08-01T12:00:00+00:00",
            ),
        )
        assert score_id == 1

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, login: str, role: str) -> None:
    resp = client.post("/api/auth/dev-login", json={"login": login, "role": role})
    assert resp.status_code == 200, resp.text


def test_password_login_with_seeded_user(tmp_path: Path) -> None:
    db_path = tmp_path / "login.db"
    os.environ["WATCHGATE_DASHBOARD_DB"] = str(db_path)
    os.environ["WATCHGATE_DASHBOARD_SEED"] = "1"
    try:
        with database.db_session(db_path) as conn:
            database.init_db(conn)
            database.seed_demo(conn)

        app = create_app()
        with TestClient(app) as client:
            bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            assert bad.status_code == 401
            ok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            assert ok.status_code == 200
            assert client.get("/api/repos").status_code == 200
            assert len(client.get("/api/repos").json()) >= 2
            scores = client.get("/api/repos/acme/payments-api/scores")
            assert scores.status_code == 200
            assert len(scores.json()) >= 3
            assert scores.json()[0].get("author_login")
    finally:
        os.environ["WATCHGATE_DASHBOARD_SEED"] = "0"


def test_revisor_can_list_scores_but_not_feedback_or_settings_or_admin(client: TestClient) -> None:
    _login(client, "viewer", "revisor")

    assert client.get("/api/repos").status_code == 200
    assert client.get("/api/repos/acme/payments-api/scores").status_code == 200
    assert client.get("/api/repos/acme/payments-api/settings").status_code == 200

    # Ajustar pesos: ✗
    assert (
        client.put(
            "/api/repos/acme/payments-api/settings",
            json={
                "weights": {"static": 1, "deps": 0, "reputation": 0, "semantic": 0},
                "thresholds": {"amarillo": 34, "rojo": 66},
            },
        ).status_code
        == 403
    )

    # Feedback: ✗
    assert client.post("/api/scores/1/feedback", json={"feedback": "correcto"}).status_code == 403

    # Gestionar accesos: ✗
    assert client.get("/api/admin/roles").status_code == 403
    assert (
        client.put(
            "/api/admin/roles",
            json={"user_login": "x", "repo": "acme/payments-api", "role": "revisor"},
        ).status_code
        == 403
    )


def test_mantenedor_can_feedback_but_not_settings_or_admin(client: TestClient) -> None:
    _login(client, "maint", "mantenedor")

    assert client.get("/api/repos/acme/payments-api/scores").status_code == 200
    assert (
        client.post("/api/scores/1/feedback", json={"feedback": "falso_positivo"}).status_code
        == 200
    )

    # Pesos/umbrales solo admin
    assert (
        client.put(
            "/api/repos/acme/payments-api/settings",
            json={
                "weights": {
                    "static": 0.3,
                    "deps": 0.2,
                    "reputation": 0.15,
                    "semantic": 0.35,
                },
                "thresholds": {"amarillo": 30, "rojo": 70},
            },
        ).status_code
        == 403
    )
    assert client.get("/api/admin/roles").status_code == 403


def test_admin_can_manage_roles_and_settings(client: TestClient) -> None:
    _login(client, "admin", "admin_organizacion")

    assert client.get("/api/repos/acme/payments-api/scores").status_code == 200
    assert client.post("/api/scores/1/feedback", json={"feedback": "correcto"}).status_code == 200
    assert client.get("/api/admin/roles").status_code == 200
    assert (
        client.put(
            "/api/admin/roles",
            json={
                "user_login": "nuevo",
                "repo": "acme/payments-api",
                "role": "revisor",
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/repos/acme/payments-api/settings",
            json={
                "weights": {
                    "static": 0.3,
                    "deps": 0.2,
                    "reputation": 0.15,
                    "semantic": 0.35,
                },
                "thresholds": {"amarillo": 30, "rojo": 70},
                "layers_enabled": {
                    "static": True,
                    "deps": True,
                    "reputation": True,
                    "semantic": True,
                },
                "block_on_high": True,
                "require_feedback_on_high": False,
            },
        ).status_code
        == 200
    )
    defaults = client.get("/api/settings/defaults")
    assert defaults.status_code == 200
    assert (
        client.put(
            "/api/settings/defaults",
            json=defaults.json(),
        ).status_code
        == 200
    )
    assert client.get("/api/metrics").status_code == 200
    metrics = client.get("/api/metrics").json()
    assert metrics["total_prs"] >= 1
    assert client.get("/api/settings/llm").status_code == 200
    llm = client.put(
        "/api/settings/llm",
        json={
            "provider": "openai",
            "model": "gpt-4.1",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-secret-key-1234",
            "monthly_budget_tokens": 1000000,
            "max_diff_tokens": 50000,
        },
    )
    assert llm.status_code == 200
    body = llm.json()
    assert body["provider"] == "openai"
    assert body["api_key_set"] is True
    assert "sk-test-secret-key-1234" not in str(body)
    assert body["api_key_masked"]
    ui = client.get("/api/settings/ui")
    assert ui.status_code == 200
    assert (
        client.put(
            "/api/settings/ui",
            json={
                "primary_color": "#255f99",
                "accent_color": "#4d6b82",
                "radius": "lg",
                "font_scale": "sm",
                "density": "compact",
                "default_theme": "dark",
            },
        ).status_code
        == 200
    )


def test_revisor_cannot_see_unassigned_repo(client: TestClient) -> None:
    _login(client, "viewer", "revisor")
    assert client.get("/api/repos/acme/auth-service/scores").status_code == 403
    assert client.get("/api/metrics").status_code == 200
    assert client.get("/api/settings/llm").status_code == 403


def test_mantenedor_cannot_edit_llm(client: TestClient) -> None:
    _login(client, "maint", "mantenedor")
    assert client.get("/api/settings/llm").status_code == 403
    assert (
        client.put(
            "/api/settings/llm",
            json={"provider": "local", "model": "llama3.1"},
        ).status_code
        == 403
    )
    assert client.get("/api/settings/ui").status_code == 200
    assert (
        client.put(
            "/api/settings/ui",
            json={
                "primary_color": "#000000",
                "accent_color": "#111111",
                "radius": "md",
                "font_scale": "md",
                "density": "comfortable",
                "default_theme": "light",
            },
        ).status_code
        == 403
    )