"""Test de aceptación §13: los 3 roles contra los endpoints de permisos."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine

# DB aislada por proceso de test.
os.environ["WATCHGATE_DASHBOARD_DB"] = str(Path(__file__).resolve().parent / "_dashboard_test.db")
os.environ["WATCHGATE_DASHBOARD_DEV_MODE"] = "1"
os.environ["WATCHGATE_DASHBOARD_SEED"] = "0"
os.environ["WATCHGATE_DASHBOARD_SECRET"] = "test-secret"


import watchgate.db.connection as db_connection  # noqa: E402
from watchgate.dashboard.backend import db as database  # noqa: E402
from watchgate.dashboard.backend.main import create_app  # noqa: E402


def _isolate_db_connection_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`create_app()` dispara, en su `lifespan`, `init_db()` de
    `watchgate/db/connection.py` (esquema de API keys/agentes, aparte del
    que gestiona `watchgate/dashboard/backend/db.py` con `sqlite3` crudo).
    `default_engine` de ese módulo es un singleton construido una sola vez
    al importarse -- fijar `WATCHGATE_DATABASE_URL` por test no tiene
    ningún efecto una vez importado, así que sin parchear `default_engine`
    directamente, cada test de este fichero termina tocando el mismo
    `.watchgate/app.db` real y compartido del checkout local (no un
    fixture aislado), exactamente el mismo patrón que ya documenta y evita
    `tests/integration/test_dashboard_api_keys.py`."""
    fresh_engine = create_engine(
        f"sqlite:///{tmp_path / 'app.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db_connection, "default_engine", fresh_engine)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    _isolate_db_connection_engine(monkeypatch, tmp_path)
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


def test_password_login_with_seeded_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate_db_connection_engine(monkeypatch, tmp_path)
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

    # Mismo usuario, distinta may/min y espacios -- no debe crear una
    # segunda fila (normalize_login en schemas.py + db.py).
    dup = client.put(
        "/api/admin/roles",
        json={"user_login": "  Nuevo  ", "repo": "acme/payments-api", "role": "mantenedor"},
    )
    assert dup.status_code == 200
    assert dup.json()["user_login"] == "nuevo"
    matching = [
        r for r in client.get("/api/admin/roles").json() if r["repo"] == "acme/payments-api"
    ]
    assert sum(1 for r in matching if r["user_login"] == "nuevo") == 1
    assert next(r for r in matching if r["user_login"] == "nuevo")["role"] == "mantenedor"

    # DELETE recibe el login como parámetro de ruta, no por RepoRoleIn --
    # comprueba que también ahí "NUEVO" borra al mismo "nuevo".
    assert client.delete("/api/admin/roles/NUEVO/acme/payments-api").status_code == 204
    assert not any(
        r["user_login"] == "nuevo" and r["repo"] == "acme/payments-api"
        for r in client.get("/api/admin/roles").json()
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
    logo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    put_ui = client.put(
        "/api/settings/ui",
        json={
            "primary_color": "#255f99",
            "accent_color": "#4d6b82",
            "radius": "lg",
            "font_scale": "sm",
            "density": "compact",
            "default_theme": "dark",
            "logo_data_url": logo,
        },
    )
    assert put_ui.status_code == 200
    assert put_ui.json()["logo_data_url"] == logo
    assert client.get("/api/settings/ui").json()["logo_data_url"] == logo

    invalid_logo = client.put(
        "/api/settings/ui",
        json={
            "primary_color": "#255f99",
            "accent_color": "#4d6b82",
            "radius": "lg",
            "font_scale": "sm",
            "density": "compact",
            "default_theme": "dark",
            "logo_data_url": "not-a-data-url",
        },
    )
    assert invalid_logo.status_code == 422


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


def _ingest_payload(repo: str = "acme/payments-api", pr_id: str = "99") -> dict:
    return {
        "result": {
            "score": 12,
            "semaforo": "verde",
            "layer_results": {
                "semantic": {
                    "layer_name": "semantic",
                    "risk_score": 12,
                    "justification": "sin hallazgos",
                    "skipped": False,
                }
            },
            "weights_used": {"semantic": 1.0},
            "pr_id": pr_id,
            "repo": repo,
            "timestamp": "2026-08-06T00:00:00+00:00",
        },
        "author_login": "ci-bot",
    }


def test_ingest_score_open_when_no_token_configured(client: TestClient) -> None:
    """Config del fixture `client`: sin WATCHGATE_DASHBOARD_INGEST_TOKEN --
    ingest_score debe aceptar la llamada sin ninguna cabecera Authorization,
    igual que hará la Action cuando el operador no active el token (dev)."""
    resp = client.post("/api/scores", json=_ingest_payload())
    assert resp.status_code == 201, resp.text
    assert resp.json()["repo"] == "acme/payments-api"


def test_ingest_score_requires_bearer_token_when_configured(
    monkeypatch, tmp_path: Path
) -> None:
    _isolate_db_connection_engine(monkeypatch, tmp_path)
    db_path = tmp_path / "ingest.db"
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(db_path))
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SEED", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "secreto-ci")

    app = create_app()
    with TestClient(app) as ingest_client:
        no_auth = ingest_client.post("/api/scores", json=_ingest_payload())
        assert no_auth.status_code == 401

        wrong_auth = ingest_client.post(
            "/api/scores",
            json=_ingest_payload(),
            headers={"Authorization": "Bearer token-incorrecto"},
        )
        assert wrong_auth.status_code == 401

        ok = ingest_client.post(
            "/api/scores",
            json=_ingest_payload(),
            headers={"Authorization": "Bearer secreto-ci"},
        )
        assert ok.status_code == 201, ok.text


def test_ci_config_returns_settings_with_dashboard_naming_convention(
    monkeypatch, tmp_path: Path
) -> None:
    """GET /repos/{repo}/ci-config es lo que consume dashboard_settings_client.py
    en la Action -- devuelve las claves propias del dashboard ("deps",
    "amarillo"/"rojo"); la traducción a la convención del motor
    ("dependencies", "yellow"/"red") es responsabilidad del cliente, no de
    este endpoint (ver test_dashboard_settings_client.py)."""
    _isolate_db_connection_engine(monkeypatch, tmp_path)
    db_path = tmp_path / "ci_config.db"
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(db_path))
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SEED", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "secreto-ci")

    with database.db_session(db_path) as conn:
        settings = database.get_settings(conn, "acme/payments-api")
        settings.layers_enabled["deps"] = False
        settings.thresholds = {"amarillo": 30, "rojo": 80}
        database.set_settings(conn, "acme/payments-api", settings)

    app = create_app()
    with TestClient(app) as ci_client:
        no_auth = ci_client.get("/api/repos/acme/payments-api/ci-config")
        assert no_auth.status_code == 401

        ok = ci_client.get(
            "/api/repos/acme/payments-api/ci-config",
            headers={"Authorization": "Bearer secreto-ci"},
        )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["layers_enabled"]["deps"] is False
        assert body["thresholds"] == {"amarillo": 30, "rojo": 80}
        assert body["monthly_budget_tokens"] == 2_000_000  # default de llm_settings
        assert "api_key" not in body and "api_key_masked" not in body