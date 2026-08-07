"""Tests unitarios para la gestión de API Keys en el Dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.main import app
from watchgate.dashboard.backend.routers.keys import get_db_session
from watchgate.dashboard.backend.schemas import User as DashboardUser


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
