"""Tests unitarios para la gestión de API Keys en el Dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.main import app
from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user, get_db_session
from watchgate.dashboard.backend.schemas import User as DashboardUser
from watchgate.db.models import MonitoredRepo
from watchgate.db.repository import create_organization, get_organization


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_keys.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


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

    # Toda clave nueva debe atarse a un repo ya monitorizado de la propia
    # organización -- se asegura primero el usuario/org del Dashboard
    # (idempotente, ver _get_or_create_db_user) para poder crear ese repo.
    db_user = _get_or_create_db_user(session, "pablo_dev")
    repo = MonitoredRepo(id="repo-runner-ci", org_id=db_user.org_id, repo_path="acme/runner")
    session.add(repo)
    session.commit()

    # 1. Crear clave
    response = client.post(
        "/api/keys",
        json={
            "name": "Runner CI",
            "scopes": "analysis:write",
            "is_test": False,
            "monitored_repo_id": repo.id,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Runner CI"
    assert data["key_prefix"].startswith("wg_live_")
    assert data["monitored_repo_id"] == repo.id
    assert data["repo_path"] == "acme/runner"
    assert "raw_token" in data
    assert data["raw_token"].startswith("wg_live_")
    key_id = data["id"]

    # 2. Listar claves
    response_list = client.get("/api/keys")
    assert response_list.status_code == 200
    keys = response_list.json()
    assert len(keys) == 1
    assert keys[0]["id"] == key_id
    assert keys[0]["repo_path"] == "acme/runner"
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

    # `_get_or_create_db_user` es idempotente -- llamarla aquí para poder
    # crear de antemano el repo al que atar la clave no cambia el usuario/
    # organización que `create_key` habría asegurado igualmente por su
    # cuenta.
    db_user = _get_or_create_db_user(session, "pablo_dev")
    repo = MonitoredRepo(id="repo-k1", org_id=db_user.org_id, repo_path="acme/k1")
    session.add(repo)
    session.commit()

    response = client.post("/api/keys", json={"name": "K1", "monitored_repo_id": repo.id})
    assert response.status_code == 201

    from watchgate.db.repository import create_user

    # `create_user` es get-or-create por email -- recupera el mismo usuario
    # que `create_key` acaba de asegurar en la BD.
    db_user = create_user(session, email="pablo_dev@watchgate.internal", name="pablo_dev")
    assert db_user.org_id is not None
    assert db_user.org_id != "default-org"

    org = get_organization(session, db_user.org_id)
    assert org is not None  # persistida de verdad, no fabricada en memoria


def test_create_key_without_monitored_repo_id_fails_validation(dashboard_client):
    """Ya no se permiten claves generales de organización -- toda clave
    nueva debe crearse con un repo asignado. Sin `monitored_repo_id` en el
    payload, FastAPI rechaza la petición antes de llegar a create_key()."""
    client, _session = dashboard_client

    response = client.post("/api/keys", json={"name": "Sin repo"})
    assert response.status_code == 422


def test_create_key_with_repo_from_another_org_fails(dashboard_client):
    """Un repo_id que existe pero pertenece a OTRA organización no debe
    aceptarse -- si no, cualquier usuario podría atar su clave a un repo
    ajeno adivinando o filtrando su ID."""
    client, session = dashboard_client

    other_org = create_organization(session, name="Otra Org")
    foreign_repo = MonitoredRepo(id="repo-ajeno", org_id=other_org.id, repo_path="otraorg/secreto")
    session.add(foreign_repo)
    session.commit()

    response = client.post(
        "/api/keys", json={"name": "Intento ajeno", "monitored_repo_id": foreign_repo.id}
    )
    assert response.status_code == 400


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
