"""Tests para GET /api/metrics/agent-usage (watchgate/dashboard/backend/routers/metrics.py).

Auditoría (hallazgo crítico, corregido): este endpoint no comprobaba
ningún rol -- cualquier usuario autenticado, sin rol en ningún repo, veía
el consumo de tokens/coste de TODA la plataforma y emails reales de otras
cuentas (confirmado en vivo contra un dashboard-backend real). El dato es
de INSTANCIA completa (compute_agent_metrics agrega toda la Engine DB, sin
concepto de organización), así que exige superadmin de sitio
(`org_scope.py::is_site_superadmin`) -- ningún rol de `repo_roles` basta.
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
def metrics_client(engine_db_session, tmp_path):
    login = "test-metrics-no-role-user"
    mock_user = DashboardUser(login=login)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: engine_db_session

    # `tmp_path` real, no la base de datos por defecto del contenedor --
    # sin esto, este fixture escribe roles de prueba en una base de datos
    # compartida (Postgres real, o un fichero SQLite local persistente
    # entre corridas), en vez de una aislada por test.
    dashboard_db_path = tmp_path / "dashboard.db"

    client = TestClient(app)
    yield client, login, dashboard_db_path

    app.dependency_overrides.clear()


def test_agent_usage_metrics_denied_without_any_role(metrics_client) -> None:
    """El caso real explotado: un usuario autenticado sin NINGÚN rol
    asignado no debe ver métricas de plataforma."""
    client, _login, _db_path = metrics_client
    response = client.get("/api/metrics/agent-usage")
    assert response.status_code == 403


def test_agent_usage_metrics_denied_for_plain_repo_role(metrics_client) -> None:
    """Tener un rol normal (no admin) en un repo tampoco basta -- esto es
    justo lo que un `mantenedor` legítimo tiene tras el fix del auto-grant
    en tasks.py, y no debe alcanzar para ver métricas de toda la plataforma."""
    client, login, db_path = metrics_client
    with database.db_session(db_path) as conn:
        database.upsert_role(conn, login, "acme/some-other-repo", "mantenedor")
    response = client.get("/api/metrics/agent-usage")
    assert response.status_code == 403


def test_agent_usage_metrics_allowed_for_site_superadmin(metrics_client, monkeypatch) -> None:
    client, login, _db_path = metrics_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)
    response = client.get("/api/metrics/agent-usage")
    assert response.status_code == 200


def test_org_metrics_visible_to_site_superadmin_without_any_role(
    metrics_client, monkeypatch
) -> None:
    """Bug real (reproducido en vivo contra un dashboard-backend real):
    GET /api/metrics usaba `user_is_org_admin`, hardcodeado a `False` desde
    que se quitó el rol "admin_organizacion" del RBAC -- un superadmin de
    sitio sin ningún `RepoRole` propio (el caso normal: administra la
    instancia, no mantiene ningún repo en persona) veía 0 en absolutamente
    todo, aunque hubiera PRs analizados reales de OTROS usuarios. Mismo
    patrón que `routers/scores.py::list_visible_repos` ya resolvía bien
    (`is_site_superadmin` -> `is_admin`/`unscoped`)."""
    from watchgate.core.models import AggregatedResult, LayerResult, Semaforo

    client, login, db_path = metrics_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)

    # Datos de OTRO usuario, sin ningún RepoRole para `login` -- antes del
    # fix, esto seguía dando 0 en /api/metrics para el superadmin.
    with database.db_session(db_path) as conn:
        database.upsert_role(conn, "otro-usuario", "acme/repo-ajeno", "mantenedor")
        database.insert_aggregated(
            conn,
            AggregatedResult(
                score=42,
                semaforo=Semaforo.AMARILLO,
                layer_results={
                    "static": LayerResult(layer_name="static", risk_score=42, justification="")
                },
                weights_used={"static": 1.0},
                pr_id="1",
                repo="acme/repo-ajeno",
                timestamp="2026-08-01T00:00:00+00:00",
            ),
            author_login="otro-usuario",
        )

    response = client.get("/api/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["repos_count"] >= 1
    assert body["total_prs"] >= 1
