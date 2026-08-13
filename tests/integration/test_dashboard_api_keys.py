"""Test de regresión: el arranque real del dashboard debe dejar listo el
esquema de API keys (spec §13 + Tarea 5.1 de la Engine API).

`routers/keys.py` usa `watchgate/db/` (SQLModel), un esquema aparte del que
usa el resto del dashboard (`watchgate/dashboard/backend/db.py`, sqlite3
crudo). `default_engine` en `watchgate/db/connection.py` es un singleton de
módulo construido una sola vez al importarse -- fijar
`WATCHGATE_DATABASE_URL` por test no tiene ningún efecto una vez importado
(y deja un `.watchgate/app.db` real compartido entre tests si no se tiene
cuidado). Por eso aquí se parchea `default_engine` directamente en vez de
la variable de entorno, siguiendo el mismo patrón que ya usa
`tests/unit/test_engine_api.py`.

Sin `init_api_keys_db()` en el `lifespan` de `main.py`, `POST /api/keys`
fallaba con "no such table: users" en cualquier despliegue real --
`test_dashboard_keys_router.py` no lo detecta porque sobreescribe
`get_db_session` con un engine ya inicializado a mano. Este test ejercita
`create_app()` tal cual, sin ese atajo, para que una regresión del arranque
sí se detecte.
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


def _seed_repo(fresh_engine, user_login: str, repo_path: str) -> str:
    """Toda clave nueva debe atarse a un repo ya monitorizado de la propia
    organización -- asegura primero el usuario/org (idempotente, lo mismo
    que haría create_key() por su cuenta) para poder crear ese repo antes
    de emitir la clave. Devuelve el id del MonitoredRepo creado."""
    with Session(fresh_engine) as session:
        db_user = _get_or_create_db_user(session, user_login)
        repo = MonitoredRepo(
            id=f"repo-{user_login}-{repo_path.replace('/', '-')}",
            org_id=db_user.org_id,
            repo_path=repo_path,
        )
        session.add(repo)
        session.commit()
        return repo.id


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[TestClient]:
    app, fresh_engine = _app_with_fresh_schema(monkeypatch, tmp_path)
    app.dependency_overrides[get_current_user] = lambda: User(login="alice")
    with TestClient(app) as test_client:
        # El esquema (tabla `users`, etc.) lo crea `init_api_keys_db()` en el
        # `lifespan` de la app -- solo existe una vez abierto el `TestClient`
        # (que dispara ese startup), no antes.
        _seed_repo(fresh_engine, "alice", "acme/runner-ci")
        yield test_client
    app.dependency_overrides.clear()


def test_real_app_startup_creates_api_keys_schema(client: TestClient) -> None:
    """Antes del fix, esto fallaba con 500 (no such table: users)."""
    created = client.post(
        "/api/keys", json={"name": "Runner CI", "monitored_repo_id": "repo-alice-acme-runner-ci"}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["raw_token"].startswith("wg_live_")

    listed = client.get("/api/keys")
    assert listed.status_code == 200
    keys = listed.json()
    assert len(keys) == 1
    assert "raw_token" not in keys[0]


def test_keys_are_scoped_per_user(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Misma app, mismo motor: bob no debe ver las claves de alice."""
    app, fresh_engine = _app_with_fresh_schema(monkeypatch, tmp_path)

    app.dependency_overrides[get_current_user] = lambda: User(login="alice")
    with TestClient(app) as alice_client:
        alice_repo_id = _seed_repo(fresh_engine, "alice", "acme/de-alice")
        response = alice_client.post(
            "/api/keys", json={"name": "de alice", "monitored_repo_id": alice_repo_id}
        )
        assert response.status_code == 201

    app.dependency_overrides[get_current_user] = lambda: User(login="bob")
    with TestClient(app) as bob_client:
        assert bob_client.get("/api/keys").json() == []
