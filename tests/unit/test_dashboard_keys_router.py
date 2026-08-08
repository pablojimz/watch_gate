"""Tests unitarios para la gestión de API Keys en el Dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.main import app
from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user, get_db_session
from watchgate.dashboard.backend.schemas import User as DashboardUser
from watchgate.db.repository import get_organization


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_keys.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def dashboard_client(test_db_session):
    mock_user = DashboardUser(login="pablo_dev")

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    client = TestClient(app)
    yield client, test_db_session

    app.dependency_overrides.clear()


def test_create_and_list_keys(dashboard_client):
    client, session = dashboard_client

    # 1. Crear clave
    response = client.post(
        "/api/keys",
        json={"name": "Runner CI", "scopes": "analysis:write", "is_test": False},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Runner CI"
    assert data["key_prefix"].startswith("wg_live_")
    assert "raw_token" in data
    assert data["raw_token"].startswith("wg_live_")
    key_id = data["id"]

    # 2. Listar claves
    response_list = client.get("/api/keys")
    assert response_list.status_code == 200
    keys = response_list.json()
    assert len(keys) == 1
    assert keys[0]["id"] == key_id
    assert "raw_token" not in keys[0]  # No expone el token crudo

    # 3. Eliminar clave
    response_del = client.delete(f"/api/keys/{key_id}")
    assert response_del.status_code == 200
    assert response_del.json() == {"status": "deleted", "id": key_id}

    # 4. Listar de nuevo (debe estar vacía)
    response_empty = client.get("/api/keys")
    assert response_empty.status_code == 200
    assert len(response_empty.json()) == 0


def test_create_key_persists_a_real_org_not_shared_default_org(dashboard_client):
    """Caso real encontrado en revisión: `create_key` nunca pasaba `org_id`,
    así que TODAS las claves creadas desde el Dashboard caían en el mismo
    `default-org` fabricado en memoria (nunca persistido) por `auth.py` --
    clientes distintos compartían cuota de tokens entre sí sin saberlo, y
    la gobernanza corporativa nunca se llegaba a aplicar. Ahora cada
    usuario debe obtener su propia Organización real y persistida."""
    client, session = dashboard_client

    response = client.post("/api/keys", json={"name": "K1"})
    assert response.status_code == 201

    from watchgate.db.repository import create_user

    # `create_user` es get-or-create por email -- recupera el mismo usuario
    # que `create_key` acaba de asegurar en la BD.
    db_user = create_user(session, email="pablo_dev@watchgate.internal", name="pablo_dev")
    assert db_user.org_id is not None
    assert db_user.org_id != "default-org"

    org = get_organization(session, db_user.org_id)
    assert org is not None  # persistida de verdad, no fabricada en memoria


def test_get_or_create_db_user_gives_distinct_users_distinct_orgs(test_db_session):
    """Dos usuarios distintos del Dashboard nunca deben terminar compartiendo
    la misma Organización -- cada uno tiene la suya, real y persistida."""
    user_a = _get_or_create_db_user(test_db_session, "alice")
    user_b = _get_or_create_db_user(test_db_session, "bob")

    assert user_a.org_id is not None
    assert user_b.org_id is not None
    assert user_a.org_id != user_b.org_id
    assert get_organization(test_db_session, user_a.org_id) is not None
    assert get_organization(test_db_session, user_b.org_id) is not None


def test_get_or_create_db_user_is_idempotent_for_same_login(test_db_session):
    """Llamadas repetidas para el mismo login no deben crear organizaciones
    duplicadas -- `org_id` determinista (`personal-<user_id>`)."""
    first = _get_or_create_db_user(test_db_session, "carol")
    second = _get_or_create_db_user(test_db_session, "carol")

    assert first.id == second.id
    assert first.org_id == second.org_id
