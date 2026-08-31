"""Tests para /api/admin/yara-rules (watchgate/dashboard/backend/routers/yara_rules.py).

Bucle de retroalimentación: cola de revisión humana de reglas YARA
propuestas por la capa semántica -- ver visibilidad (admin_organizacion,
acotado a su propia org) vs. activación (superadmin de sitio, instancia
completa) en el docstring del propio router.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import get_current_user
from watchgate.dashboard.backend.main import app
from watchgate.dashboard.backend.routers.yara_rules import get_db_session
from watchgate.dashboard.backend.schemas import User as DashboardUser
from watchgate.db.connection import init_db
from watchgate.db.models import PendingYaraRule
from watchgate.db.repository import create_organization, create_user

_INNOCUOUS_YARA_SOURCE = """
rule marker_rule {
    strings:
        $a = "TOTALLY_UNIQUE_MARKER_STRING_998877"
    condition:
        $a
}
"""


@pytest.fixture
def engine_db_session():
    # StaticPool -- ver mismo pitfall documentado en test_dashboard_metrics_router.py.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def yara_client(engine_db_session, tmp_path, monkeypatch):
    login = "test-yara-user"
    mock_user = DashboardUser(login=login)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: engine_db_session

    # `tmp_path` real para la BD del Dashboard, vía WATCHGATE_DASHBOARD_DB
    # -- sin esto, las llamadas a database.db_session() SIN argumento que
    # el propio router hace (_require_org_admin_or_site_superadmin) irían
    # a una BD por defecto distinta de la que este fixture usa para seedear
    # roles (default_db_path() lee justo esta env var, ver db.py).
    dashboard_db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(dashboard_db_path))

    client = TestClient(app)
    yield client, login, engine_db_session, dashboard_db_path

    app.dependency_overrides.clear()


def _make_org_and_bind_user(session, login: str, org_id: str):
    org = create_organization(session, name=org_id, org_id=org_id)
    email = f"{login.lower()}@watchgate.internal"
    create_user(session, email=email, name=login, org_id=org.id)
    return org


def _add_pending_rule(
    session,
    *,
    org_id: str | None,
    rule_id: str = "rule-1",
    rule_name: str = "marker_rule",
    yara_source: str = _INNOCUOUS_YARA_SOURCE,
    status: str = "pending",
) -> PendingYaraRule:
    row = PendingYaraRule(
        id=rule_id,
        org_id=org_id,
        repo="acme/repo",
        pr_id="1",
        rule_name=rule_name,
        category="webshells",
        yara_source=yara_source,
        rationale="x",
        status=status,
    )
    session.add(row)
    session.commit()
    return row


def test_list_denied_without_any_role(yara_client) -> None:
    client, _login, _engine_session, _db_path = yara_client
    response = client.get("/api/admin/yara-rules")
    assert response.status_code == 403


def test_list_org_admin_sees_only_own_org(yara_client) -> None:
    client, login, engine_session, db_path = yara_client
    org = _make_org_and_bind_user(engine_session, login, "org-mine")
    _add_pending_rule(engine_session, org_id=org.id, rule_id="mine", rule_name="mine_rule")
    _add_pending_rule(engine_session, org_id="org-other", rule_id="theirs", rule_name="their_rule")

    with database.db_session(db_path) as conn:
        database.upsert_role(conn, login, "acme/repo", "admin_organizacion", org_id=org.id)

    response = client.get("/api/admin/yara-rules")

    assert response.status_code == 200
    rule_names = {r["rule_name"] for r in response.json()}
    assert rule_names == {"mine_rule"}


def test_list_site_superadmin_sees_all_orgs(yara_client, monkeypatch) -> None:
    client, login, engine_session, _db_path = yara_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)
    _add_pending_rule(engine_session, org_id="org-a", rule_id="a", rule_name="rule_a")
    _add_pending_rule(engine_session, org_id="org-b", rule_id="b", rule_name="rule_b")

    response = client.get("/api/admin/yara-rules")

    assert response.status_code == 200
    rule_names = {r["rule_name"] for r in response.json()}
    assert rule_names == {"rule_a", "rule_b"}


def test_approve_denied_for_org_admin(yara_client) -> None:
    """Ver la cola no basta para aprobar: activar una regla es de
    instancia completa, exige superadmin de sitio (ver docstring del
    router)."""
    client, login, engine_session, db_path = yara_client
    org = _make_org_and_bind_user(engine_session, login, "org-mine")
    row = _add_pending_rule(engine_session, org_id=org.id)
    with database.db_session(db_path) as conn:
        database.upsert_role(conn, login, "acme/repo", "admin_organizacion", org_id=org.id)

    response = client.post(f"/api/admin/yara-rules/{row.id}/approve")

    assert response.status_code == 403


def test_approve_site_superadmin_activates_rule(yara_client, monkeypatch) -> None:
    client, login, engine_session, _db_path = yara_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)
    row = _add_pending_rule(engine_session, org_id="org-a")

    response = client.post(f"/api/admin/yara-rules/{row.id}/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == login
    assert body["reviewed_at"] is not None
    assert body["benign_matches"] == []  # marcador inocuo, no coincide contra código benigno


def test_approve_flags_matches_against_benign_fixtures(yara_client, monkeypatch) -> None:
    """Una regla demasiado amplia (aquí: cualquier fichero que contenga
    'def ', típico de Python) dispara sobre los fixtures benignos -- se
    aprueba igual (la decisión sigue siendo humana), pero con el aviso."""
    client, login, engine_session, _db_path = yara_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)
    broad_source = """
rule too_broad_rule {
    strings:
        $a = "def "
    condition:
        $a
}
"""
    row = _add_pending_rule(
        engine_session, org_id="org-a", rule_name="too_broad_rule", yara_source=broad_source
    )

    response = client.post(f"/api/admin/yara-rules/{row.id}/approve")

    assert response.status_code == 200
    assert len(response.json()["benign_matches"]) > 0


def test_approve_404_for_unknown_id(yara_client, monkeypatch) -> None:
    client, login, _engine_session, _db_path = yara_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)

    response = client.post("/api/admin/yara-rules/does-not-exist/approve")

    assert response.status_code == 404


def test_approve_409_if_already_reviewed(yara_client, monkeypatch) -> None:
    client, login, engine_session, _db_path = yara_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)
    row = _add_pending_rule(engine_session, org_id="org-a", status="approved")

    response = client.post(f"/api/admin/yara-rules/{row.id}/approve")

    assert response.status_code == 409


def test_reject_site_superadmin_marks_rejected(yara_client, monkeypatch) -> None:
    client, login, engine_session, _db_path = yara_client
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", login)
    row = _add_pending_rule(engine_session, org_id="org-a")

    response = client.post(f"/api/admin/yara-rules/{row.id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_reject_denied_for_org_admin(yara_client) -> None:
    client, login, engine_session, db_path = yara_client
    org = _make_org_and_bind_user(engine_session, login, "org-mine")
    row = _add_pending_rule(engine_session, org_id=org.id)
    with database.db_session(db_path) as conn:
        database.upsert_role(conn, login, "acme/repo", "admin_organizacion", org_id=org.id)

    response = client.post(f"/api/admin/yara-rules/{row.id}/reject")

    assert response.status_code == 403
