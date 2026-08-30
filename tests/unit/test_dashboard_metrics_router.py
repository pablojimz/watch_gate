"""Tests para GET /api/metrics/agent-usage (watchgate/dashboard/backend/routers/metrics.py).

Auditoría (hallazgo crítico, corregido): este endpoint no comprobaba
ningún rol -- cualquier usuario autenticado, sin rol en ningún repo, veía
el consumo de tokens/coste de TODA la plataforma y emails reales de otras
cuentas (confirmado en vivo contra un dashboard-backend real). Ahora
exige `admin_organizacion`, mismo patrón que llm_settings.py/ui_settings.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.main import app
from watchgate.dashboard.backend.routers.metrics import get_db_session
from watchgate.dashboard.backend.schemas import User as DashboardUser
from watchgate.db.connection import init_db

# Import necesario para que SQLModel.metadata (y por tanto init_db()) sepa
# de estas tablas -- watchgate.db.models.PRScore/UserTokenUsage solo se
# importan de forma perezosa dentro de compute_agent_metrics(), así que sin
# esto el CREATE TABLE de init_db() no las crea (mismo patrón que
# test_dashboard_agent_metrics.py).
from watchgate.db.models import PRScore, UserTokenUsage  # noqa: F401


@pytest.fixture
def engine_db_session():
    # StaticPool -- SQLite en memoria es POR CONEXIÓN: sin esto, init_db()
    # (que abre y suelta su propia conexión) y el `Session(engine)` de
    # abajo podrían recibir cada uno una conexión física distinta del pool,
    # cada una con su propia base de datos en blanco -- init_db() crearía
    # las tablas en una conexión que nadie vuelve a usar. Mismo pitfall ya
    # documentado en este repo (OSVCache, vulnerabilities_layer.py).
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def metrics_client(engine_db_session):
    login = "test-metrics-no-role-user"
    mock_user = DashboardUser(login=login)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: engine_db_session

    client = TestClient(app)
    yield client, login

    app.dependency_overrides.clear()
    with database.db_session() as conn:
        database.delete_role(conn, login, "acme/some-other-repo")


def test_agent_usage_metrics_denied_without_any_role(metrics_client) -> None:
    """El caso real explotado: un usuario autenticado sin NINGÚN rol
    asignado no debe ver métricas de plataforma."""
    client, _login = metrics_client
    response = client.get("/api/metrics/agent-usage")
    assert response.status_code == 403


def test_agent_usage_metrics_denied_for_plain_repo_role(metrics_client) -> None:
    """Tener un rol normal (no admin) en un repo tampoco basta -- esto es
    justo lo que un `mantenedor` legítimo tiene tras el fix del auto-grant
    en tasks.py, y no debe alcanzar para ver métricas de toda la plataforma."""
    client, login = metrics_client
    with database.db_session() as conn:
        database.upsert_role(conn, login, "acme/some-other-repo", "mantenedor")
    response = client.get("/api/metrics/agent-usage")
    assert response.status_code == 403


def test_agent_usage_metrics_allowed_for_real_admin(metrics_client) -> None:
    client, login = metrics_client
    with database.db_session() as conn:
        database.upsert_role(conn, login, "acme/some-other-repo", "admin_organizacion")
    response = client.get("/api/metrics/agent-usage")
    assert response.status_code == 200
