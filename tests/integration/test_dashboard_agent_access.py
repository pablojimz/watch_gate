"""Test de integración real: acceso de agentes de IA al Dashboard vía API Key
(watchgate/dashboard/backend/routers/agent_access.py).

Mismo patrón que `test_dashboard_api_keys.py` (app real, `create_app()`, sin
atajos de `dependency_overrides` para la parte de API Key -- solo para
iniciar sesión de cookie una vez y poder emitir la propia API Key, que es
exactamente el flujo real: un humano crea la clave desde el Dashboard, luego
un agente la usa por HTTP).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

import watchgate.db.connection as db_connection
from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
from watchgate.dashboard.backend.schemas import User
from watchgate.db.models import MonitoredRepo

_DASHBOARD_ENV = {
    "WATCHGATE_DASHBOARD_DEV_MODE": "1",
    "WATCHGATE_DASHBOARD_SEED": "0",
    "WATCHGATE_DASHBOARD_SECRET": "test-secret",
}


def _app_with_fresh_schema(monkeypatch: pytest.MonkeyPatch, tmp_path):
    for key, value in _DASHBOARD_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(tmp_path / "dashboard.db"))

    fresh_engine = create_engine(
        f"sqlite:///{tmp_path / 'app.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db_connection, "default_engine", fresh_engine)

    from watchgate.dashboard.backend.main import create_app

    return create_app(), fresh_engine


@pytest.fixture()
def app_and_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[tuple]:  # type: ignore[type-arg]
    app, fresh_engine = _app_with_fresh_schema(monkeypatch, tmp_path)

    app.dependency_overrides[get_current_user] = lambda: User(login="alice")
    with TestClient(app) as human_client:
        # El esquema (tabla `users`, etc.) lo crea `init_api_keys_db()` en el
        # `lifespan` de la app -- solo existe una vez abierto el
        # `TestClient` (que dispara ese startup), no antes. Toda clave nueva
        # debe atarse a un repo ya monitorizado -- se asegura primero el
        # usuario/org de "alice" (idempotente, lo mismo que haría
        # create_key() por su cuenta) para poder crear ese repo.
        with Session(fresh_engine) as session:
            db_user = _get_or_create_db_user(session, "alice")
            # Id fijo y conocido para poder usarlo tras cerrar la sesión sin
            # reenganchar la instancia (leer `.id` con la sesión ya cerrada
            # dispara un refresh sobre un objeto "detached").
            session.add(
                MonitoredRepo(id="repo-agent-ci", org_id=db_user.org_id, repo_path="acme/agent-ci")
            )
            session.commit()

        created = human_client.post(
            "/api/keys", json={"name": "Agente CI", "monitored_repo_id": "repo-agent-ci"}
        )
        assert created.status_code == 201, created.text
        raw_token = created.json()["raw_token"]
    app.dependency_overrides.clear()
    try:
        yield app, raw_token
    finally:
        fresh_engine.dispose()


def _seed_score(
    app, tmp_path, *, repo: str, score: int, semaforo: str, user_login: str = "alice"
) -> None:
    import os

    from watchgate.core.models import AggregatedResult, LayerResult
    from watchgate.core.models import Semaforo as SemaforoEnum
    from watchgate.dashboard.backend import db as database

    os.environ["WATCHGATE_DASHBOARD_DB"] = str(tmp_path / "dashboard.db")
    result = AggregatedResult(
        score=score,
        semaforo=SemaforoEnum(semaforo),
        pr_id="1",
        repo=repo,
        timestamp="2026-08-10T10:00:00Z",
        weights_used={"static": 1.0},
        layer_results={
            "static": LayerResult(layer_name="static", risk_score=score, justification="x")
        },
    )
    with database.db_session() as conn:
        database.insert_aggregated(conn, result, author_login="octocat")
        if user_login:
            database.upsert_role(conn, user_login, repo, "revisor")


def test_agent_access_requires_a_valid_api_key(app_and_key) -> None:
    app, _raw_token = app_and_key
    with TestClient(app) as client:
        resp = client.get("/api/agent-access/repos/acme%2Fwebapp/scores")
    assert resp.status_code == 401


def test_agent_access_rejects_garbage_bearer_token(app_and_key) -> None:
    app, _raw_token = app_and_key
    with TestClient(app) as client:
        resp = client.get(
            "/api/agent-access/repos/acme%2Fwebapp/scores",
            headers={"Authorization": "Bearer wg_live_no-existe"},
        )
    assert resp.status_code == 401


def test_agent_access_denied_without_repo_role(app_and_key, tmp_path) -> None:
    app, raw_token = app_and_key
    _seed_score(app, tmp_path, repo="acme/secret-repo", score=80, semaforo="rojo", user_login="")

    with TestClient(app) as client:
        resp = client.get(
            "/api/agent-access/repos/acme%2Fsecret-repo/scores",
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    assert resp.status_code == 403
    assert "Permiso denegado" in resp.json()["detail"]


def test_repo_score_history_via_api_key_returns_real_data(app_and_key, tmp_path) -> None:
    app, raw_token = app_and_key
    _seed_score(app, tmp_path, repo="acme/webapp", score=75, semaforo="rojo")

    with TestClient(app) as client:
        resp = client.get(
            "/api/agent-access/repos/acme%2Fwebapp/scores",
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 1
    assert data[0]["score"] == 75
    assert data[0]["semaforo"] == "rojo"


def test_repo_score_history_via_api_key_respects_limit(app_and_key, tmp_path) -> None:
    app, raw_token = app_and_key
    for score in (10, 20, 30):
        _seed_score(app, tmp_path, repo="acme/webapp", score=score, semaforo="verde")

    with TestClient(app) as client:
        resp = client.get(
            "/api/agent-access/repos/acme%2Fwebapp/scores?limit=2",
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_org_metrics_via_api_key_returns_real_data(app_and_key, tmp_path) -> None:
    app, raw_token = app_and_key
    _seed_score(app, tmp_path, repo="acme/webapp", score=75, semaforo="rojo")
    _seed_score(app, tmp_path, repo="acme/otro", score=5, semaforo="verde")

    with TestClient(app) as client:
        resp = client.get(
            "/api/agent-access/metrics", headers={"Authorization": f"Bearer {raw_token}"}
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_prs"] == 2
    assert data["repos_count"] == 2


def test_org_metrics_via_api_key_scoped_to_explicit_repos(app_and_key, tmp_path) -> None:
    app, raw_token = app_and_key
    _seed_score(app, tmp_path, repo="acme/webapp", score=75, semaforo="rojo")
    _seed_score(app, tmp_path, repo="acme/otro", score=5, semaforo="verde")

    with TestClient(app) as client:
        resp = client.get(
            "/api/agent-access/metrics?repos=acme/webapp",
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_prs"] == 1
    assert data["repos_count"] == 1


def test_agent_access_also_accepts_x_api_key_header(app_and_key, tmp_path) -> None:
    app, raw_token = app_and_key
    _seed_score(app, tmp_path, repo="acme/webapp", score=42, semaforo="amarillo")

    with TestClient(app) as client:
        resp = client.get(
            "/api/agent-access/repos/acme%2Fwebapp/scores",
            headers={"X-API-Key": raw_token},
        )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
