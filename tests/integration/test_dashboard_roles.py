"""Test de aceptación §13: los 3 roles contra los endpoints de permisos."""

from __future__ import annotations

import os
from collections.abc import Iterator
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


def _isolate_db_connection_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    fresh_engine = create_engine(
        f"sqlite:///{tmp_path / 'app.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db_connection, "default_engine", fresh_engine)
    return fresh_engine


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    fresh_engine = _isolate_db_connection_engine(monkeypatch, tmp_path)
    db_path = tmp_path / "dashboard.db"
    os.environ["WATCHGATE_DASHBOARD_DB"] = str(db_path)

    with database.db_session(db_path) as conn:
        database.init_db(conn)
        database.upsert_role(conn, "admin", "acme/payments-api", "mantenedor")
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

    fresh_engine.dispose()


def _login(client: TestClient, login: str, role: str) -> None:
    resp = client.post("/api/auth/dev-login", json={"login": login, "role": role})
    assert resp.status_code == 200, resp.text


def _connect_repo_to_admin_org(repo_path: str) -> None:
    """Da de alta un `MonitoredRepo` para `repo_path` bajo la organización
    real de "admin" -- `_require_role_manager` (feedback.py, PUT/DELETE
    /admin/roles) exige que el repo sobre el que se concede/revoca un rol
    resuelva a la MISMA organización que quien llama
    (`resolve_org_id_for_repo`, org_scope.py), y eso solo se resuelve vía
    una fila `MonitoredRepo` real -- nunca sobre un repo que solo existe
    por ingesta de CI (fail-closed, por diseño; ver el docstring de
    `resolve_org_id_for_repo`). Los tests que llaman a esto necesitan que
    su repo esté "conectado"; deliberadamente NO se hace en el fixture
    `client` para no interferir con
    `test_admin_roles_list_shows_connected_repo_type`, que depende de que
    acme/payments-api NO tenga `MonitoredRepo`."""
    from sqlmodel import Session

    from watchgate.db.models import MonitoredRepo
    from watchgate.dashboard.backend.org_scope import resolve_caller_org_id

    with Session(db_connection.default_engine) as session:
        org_id = resolve_caller_org_id(session, "admin")
        session.add(
            MonitoredRepo(
                id=f"mr-{repo_path.replace('/', '-')}",
                org_id=org_id,
                repo_path=repo_path,
                monitor_type="managed",
                status="active",
            )
        )
        session.commit()


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
            ok = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123"})
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

    # Aceptar (gate de aprobación manual): ✗
    assert client.post("/api/scores/1/accept").status_code == 403

    # Gestionar accesos: ✗
    assert client.get("/api/admin/roles").status_code == 403
    assert (
        client.put(
            "/api/admin/roles",
            json={"user_login": "x", "repo": "acme/payments-api", "role": "revisor"},
        ).status_code
        == 403
    )


def test_mantenedor_can_feedback_and_own_repo_settings_but_not_global_admin(
    client: TestClient,
) -> None:
    _login(client, "maint", "mantenedor")

    assert client.get("/api/repos/acme/payments-api/scores").status_code == 200
    assert (
        client.post("/api/scores/1/feedback", json={"feedback": "falso_positivo"}).status_code
        == 200
    )

    # Pesos/umbrales de SU repo: el dueño del repo (mantenedor) decide.
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
        == 200
    )
    # Listado global de roles: solo superadmin de sitio.
    assert client.get("/api/admin/roles").status_code == 403


def test_mantenedor_can_accept_and_unaccept_score(client: TestClient) -> None:
    _login(client, "maint", "mantenedor")

    accepted = client.post("/api/scores/1/accept")
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["accepted_by"] == "maint"
    assert body["accepted_at"] is not None
    # "acme/payments-api" no tiene MonitoredRepo/VCSConnection en la
    # Engine DB de este test -- nada que mergear, mismo comportamiento
    # que antes de añadir el merge automático al aceptar.
    assert body["merge_attempted"] is False
    assert body["merged"] is None

    cleared = client.delete("/api/scores/1/accept")
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["accepted_by"] is None
    assert body["accepted_at"] is None


def _add_monitored_repo_with_connection(repo_path: str, access_token: str) -> None:
    """Crea MonitoredRepo + VCSConnection reales en la Engine DB (motor
    aislado de este test, ver `_isolate_db_connection_engine`) -- crea las
    tablas primero porque el fixture `client` no las migra (solo usa la
    Engine DB para roles/settings, nunca para MonitoredRepo en los tests
    de este fichero antes de esto)."""
    import watchgate.db.crypto
    from cryptography.fernet import Fernet
    from sqlmodel import Session

    from watchgate.db.connection import SQLModel
    from watchgate.db.models import MonitoredRepo, Organization, VCSConnection

    # VCSConnection.access_token es EncryptedString -- necesita una clave
    # Fernet configurada, igual que en test_repos_scan.py.
    watchgate.db.crypto._fernet = Fernet("1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=")

    engine = db_connection.default_engine
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = Organization(id="org-merge-test", name="Org Merge Test")
        session.add(org)
        vcs = VCSConnection(id="vcs-merge-test", org_id=org.id, access_token=access_token)
        session.add(vcs)
        session.add(
            MonitoredRepo(
                id="repo-merge-test",
                org_id=org.id,
                vcs_connection_id=vcs.id,
                repo_path=repo_path,
                monitor_type="managed",
            )
        )
        session.commit()


def test_accept_score_merges_real_pr_when_repo_has_github_connection(
    client: TestClient,
) -> None:
    """Repo con VCSConnection real + PR numérico -- accept_score debe
    intentar el merge de verdad (mockeando solo la llamada HTTP a GitHub,
    no la resolución de credenciales)."""
    from unittest.mock import patch

    from watchgate.core.models import AggregatedResult, Semaforo
    from watchgate.dashboard.backend import db as database

    _add_monitored_repo_with_connection("acme/merge-repo", access_token="tok_merge_test")

    with database.db_session() as conn:
        score_id = database.insert_aggregated(
            conn,
            AggregatedResult(
                score=80,
                semaforo=Semaforo.ROJO,
                layer_results={},
                weights_used={},
                pr_id="7",
                repo="acme/merge-repo",
                timestamp="2026-08-27T12:00:00+00:00",
            ),
        )
        database.upsert_role(conn, "maint", "acme/merge-repo", "mantenedor")

    _login(client, "maint", "mantenedor")

    with patch(
        "watchgate.dashboard.backend.routers.feedback.GitHubClient.merge_pull_request",
        return_value={"merged": True},
    ) as mock_merge:
        response = client.post(f"/api/scores/{score_id}/accept")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted_by"] == "maint"
    assert body["merge_attempted"] is True
    assert body["merged"] is True
    assert body["merge_message"] is None
    mock_merge.assert_called_once_with("acme", "merge-repo", 7)


def test_accept_score_reports_merge_failure_without_losing_acceptance(
    client: TestClient,
) -> None:
    """Si GitHub rechaza el merge (rama protegida, conflictos...), el
    accept en sí sigue quedando registrado -- solo se reporta el fallo."""
    from unittest.mock import patch

    from watchgate.core.models import AggregatedResult, Semaforo
    from watchgate.dashboard.backend import db as database

    _add_monitored_repo_with_connection("acme/merge-fail-repo", access_token="tok_merge_test")

    with database.db_session() as conn:
        score_id = database.insert_aggregated(
            conn,
            AggregatedResult(
                score=80,
                semaforo=Semaforo.ROJO,
                layer_results={},
                weights_used={},
                pr_id="9",
                repo="acme/merge-fail-repo",
                timestamp="2026-08-27T12:00:00+00:00",
            ),
        )
        database.upsert_role(conn, "maint", "acme/merge-fail-repo", "mantenedor")

    _login(client, "maint", "mantenedor")

    with patch(
        "watchgate.dashboard.backend.routers.feedback.GitHubClient.merge_pull_request",
        side_effect=RuntimeError("405 Method Not Allowed"),
    ):
        response = client.post(f"/api/scores/{score_id}/accept")

    assert response.status_code == 200, response.text
    body = response.json()
    # La aceptación humana queda registrada aunque el merge fallase.
    assert body["accepted_by"] == "maint"
    assert body["merge_attempted"] is True
    assert body["merged"] is False
    assert body["merge_message"]


def test_admin_can_manage_roles_and_settings(client: TestClient) -> None:
    _login(client, "admin", "mantenedor")
    _connect_repo_to_admin_org("acme/payments-api")

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


def test_admin_can_manage_users(client: TestClient) -> None:
    _login(client, "admin", "mantenedor")

    assert client.get("/api/admin/users").status_code == 200

    created = client.post(
        "/api/admin/users",
        json={"login": "Nueva.Persona", "display_name": "Nueva Persona", "password": "correcto123"},
    )
    assert created.status_code == 201
    body = created.json()
    # normalize_login: minúsculas, sin espacios -- mismo criterio que roles.
    assert body["login"] == "nueva.persona"
    assert body["display_name"] == "Nueva Persona"
    assert "password" not in body and "password_hash" not in body

    listed = client.get("/api/admin/users").json()
    assert any(u["login"] == "nueva.persona" for u in listed)

    # Login duplicado (aunque con distinta may/min) -> 409, no lo pisa.
    dup = client.post(
        "/api/admin/users",
        json={"login": "NUEVA.PERSONA", "display_name": "Otra", "password": "correcto123"},
    )
    assert dup.status_code == 409

    # Contraseña corta -> 422 (validación de schema, min_length=8).
    weak = client.post(
        "/api/admin/users",
        json={"login": "otra-persona", "display_name": "Otra", "password": "1234567"},
    )
    assert weak.status_code == 422

    # No se puede borrar la propia cuenta desde aquí.
    assert client.delete("/api/admin/users/admin").status_code == 400

    assert client.delete("/api/admin/users/nueva.persona").status_code == 204
    assert not any(u["login"] == "nueva.persona" for u in client.get("/api/admin/users").json())
    assert client.delete("/api/admin/users/nueva.persona").status_code == 404


def test_admin_can_assign_an_initial_role_when_creating_a_user(client: TestClient) -> None:
    """`repo`/`role` en POST /api/admin/users son opcionales -- si se pasan
    los dos, el alta asigna ese rol inicial en el mismo paso (mismo
    upsert_role que la gestión de roles por repo, PUT /api/admin/roles, ya
    usaba por separado), sin bloquear la creación de usuarios sin rol."""
    _login(client, "admin", "mantenedor")
    _connect_repo_to_admin_org("acme/payments-api")

    created = client.post(
        "/api/admin/users",
        json={
            "login": "con.rol",
            "display_name": "Con Rol",
            "password": "correcto123",
            "repo": "acme/payments-api",
            "role": "mantenedor",
        },
    )
    assert created.status_code == 201

    roles = client.get("/api/admin/roles").json()
    assert any(
        r["user_login"] == "con.rol"
        and r["repo"] == "acme/payments-api"
        and r["role"] == "mantenedor"
        for r in roles
    )

    # Sin repo/role (los dos opcionales, por defecto None) -- se crea sin
    # ningún rol asignado, comportamiento de siempre.
    created_without_role = client.post(
        "/api/admin/users",
        json={"login": "sin.rol", "display_name": "Sin Rol", "password": "correcto123"},
    )
    assert created_without_role.status_code == 201
    roles_after = client.get("/api/admin/roles").json()
    assert not any(r["user_login"] == "sin.rol" for r in roles_after)


def test_admin_roles_list_shows_connected_repo_type(client: TestClient) -> None:
    """/api/admin/roles enriquece cada fila con `monitor_type`, resuelto
    contra MonitoredRepo (Engine DB) por repo_path -- "audited"/"managed"
    si el repo está conectado en Auditoría Externa, `None` si no (p. ej.
    llegó por ingesta directa del adaptador de CI, como acme/payments-api
    en este mismo fixture)."""
    from sqlmodel import Session

    from watchgate.db.models import MonitoredRepo, Organization

    with Session(db_connection.default_engine) as session:
        org = Organization(id="org-roles-test", name="Org Roles Test")
        session.add(org)
        session.add(
            MonitoredRepo(
                id="repo-roles-test",
                org_id=org.id,
                repo_path="acme/auth-service",
                monitor_type="audited",
                status="active",
            )
        )
        session.commit()

    _login(client, "admin", "mantenedor")
    roles = client.get("/api/admin/roles").json()

    auth_service_role = next(r for r in roles if r["repo"] == "acme/auth-service")
    assert auth_service_role["monitor_type"] == "audited"

    # acme/payments-api tiene rol asignado (seed del fixture `client`) pero
    # nunca se conectó como repo externo -- no está en MonitoredRepo.
    payments_role = next(r for r in roles if r["repo"] == "acme/payments-api")
    assert payments_role["monitor_type"] is None


def test_revisor_and_mantenedor_cannot_manage_users(client: TestClient) -> None:
    _login(client, "viewer", "revisor")
    assert client.get("/api/admin/users").status_code == 403
    assert (
        client.post(
            "/api/admin/users",
            json={"login": "x", "display_name": "X", "password": "correcto123"},
        ).status_code
        == 403
    )
    assert client.delete("/api/admin/users/admin").status_code == 403

    _login(client, "maint", "mantenedor")
    assert client.get("/api/admin/users").status_code == 403


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


def test_ingest_score_requires_bearer_token_when_configured(monkeypatch, tmp_path: Path) -> None:
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


def test_findings_survive_the_round_trip_through_pr_scores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`pr_scores` solo tenía columnas planas por capa (score/skipped) --
    `findings` (fichero/línea/regla), `category`, `confidence` y
    `threat_nature` se perdían al insertar, aunque el análisis original los
    tuviera. Sin esto, un botón "ver reporte" en el dashboard no podría
    mostrar nada más sustancioso de lo que ya cabe en la fila de la tabla."""
    from watchgate.core.models import (
        AggregatedResult,
        Confidence,
        Finding,
        LayerResult,
        RiskCategory,
        Semaforo,
        ThreatNature,
    )

    _isolate_db_connection_engine(monkeypatch, tmp_path)
    db_path = tmp_path / "findings.db"

    result = AggregatedResult(
        score=95,
        semaforo=Semaforo.ROJO,
        pr_id="7",
        repo="acme/payments-api",
        timestamp="2026-08-10T10:00:00+00:00",
        weights_used={"semantic": 1.0},
        threat_summary={"malicioso": 1, "vulnerabilidad": 0, "incertidumbre": 0},
        layer_results={
            "semantic": LayerResult(
                layer_name="semantic",
                risk_score=95,
                justification="Backdoor con exfiltración de credenciales.",
                findings=[
                    Finding(
                        file_path="src/utils.py",
                        line=10,
                        rule_id="exfil-curl-bash",
                        message="curl | bash con credenciales codificadas",
                        severity="error",
                        threat_nature=ThreatNature.MALICIOUS,
                    )
                ],
                category=RiskCategory.EXFILTRACION,
                confidence=Confidence.ALTA,
                threat_nature=ThreatNature.MALICIOUS,
            )
        },
    )

    with database.db_session(db_path) as conn:
        score_id = database.insert_aggregated(conn, result, author_login="mirrorbot")
        fetched = database.get_score(conn, score_id)

    assert fetched is not None
    semantic = fetched.layer_results["semantic"]
    assert semantic["threat_nature"] == "malicioso"
    assert semantic["category"] == "exfiltracion"
    assert semantic["confidence"] == "alta"
    assert len(semantic["findings"]) == 1
    assert semantic["findings"][0]["rule_id"] == "exfil-curl-bash"
    assert semantic["findings"][0]["line"] == 10
