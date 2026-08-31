"""Tests unitarios para el escaneo bajo demanda de repositorios externos.

Antes cubría también el repolling PERIÓDICO automático (scheduler +
auto_scan_prs + scan_interval_minutes) -- eliminado a petición explícita:
todo escaneo de un repo ya conectado requiere pulsar "Escanear" en el
Dashboard. Ver `watchgate/service/repo_polling.py`.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session

# Configurar Fernet key para cifrado de campos de DB en tests
os.environ["WATCHGATE_DB_SECRET"] = "1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I="
import watchgate.db.crypto

watchgate.db.crypto._fernet = Fernet("1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=")

from watchgate.adapters.github_client import GitHubClient  # noqa: E402
from watchgate.dashboard.backend.main import app  # noqa: E402
from watchgate.db.connection import build_engine, get_db_session  # noqa: E402
from watchgate.db.models import (  # noqa: E402
    MonitoredRepo,
    RepoArchitectureSummary,
    RepoGraphEdge,
    RepoGraphNode,
    UserAPIKey,
    VCSConnection,
)
from watchgate.db.repository import create_organization  # noqa: E402
from watchgate.service.repo_polling import RepoPollingService  # noqa: E402


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_auto_scan.db"
    test_engine = build_engine(f"sqlite:///{db_file}")

    from watchgate.db.connection import SQLModel

    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        yield session


def test_github_client_list_pull_requests_with_etag_200():
    client = GitHubClient("fake_token")
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [{"number": 1, "title": "Test PR"}]
    mock_response.headers = {"ETag": '"etag_123"'}

    with patch.object(client, "_request", return_value=mock_response):
        prs, etag = client.list_recent_pull_requests_with_etag("owner", "repo", etag='"etag_000"')
        assert prs == [{"number": 1, "title": "Test PR"}]
        assert etag == '"etag_123"'


def test_github_client_list_pull_requests_with_etag_304():
    client = GitHubClient("fake_token")
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 304

    with patch.object(client, "_request", return_value=mock_response):
        prs, etag = client.list_recent_pull_requests_with_etag("owner", "repo", etag='"etag_123"')
        assert prs is None
        assert etag == '"etag_123"'


def test_get_candidate_repo_by_id_returns_none_for_paused_repo(test_db_session):
    """Un repo pausado no se puede escanear ni siquiera a mano -- hay que
    reactivarlo primero vía PATCH .../status=active."""
    sess_target = "watchgate.service.repo_polling.get_session"
    with patch(sess_target, side_effect=lambda: iter([test_db_session])):
        org = create_organization(test_db_session, "Org Paused")
        repo = MonitoredRepo(
            id="repo-paused",
            org_id=org.id,
            repo_path="owner/pausedrepo",
            monitor_type="audited",
            status="paused",
        )
        test_db_session.add(repo)
        test_db_session.commit()

        assert RepoPollingService.get_candidate_repo_by_id("repo-paused") is None


def test_get_candidate_repo_by_id_resolves_token_from_vcs_connection(test_db_session):
    sess_target = "watchgate.service.repo_polling.get_session"
    with patch(sess_target, side_effect=lambda: iter([test_db_session])):
        org = create_organization(test_db_session, "Org Candidate")
        vcs = VCSConnection(id="vcs-1", org_id=org.id, access_token="token_vcs")
        test_db_session.add(vcs)
        repo = MonitoredRepo(
            id="repo-1",
            org_id=org.id,
            vcs_connection_id=vcs.id,
            repo_path="owner/repo1",
            monitor_type="audited",
            status="active",
        )
        test_db_session.add(repo)
        test_db_session.commit()

        with patch.dict(os.environ, {}, clear=True):
            candidate = RepoPollingService.get_candidate_repo_by_id("repo-1")
            assert candidate is not None
            assert candidate["repo_path"] == "owner/repo1"
            assert candidate["token"] == "token_vcs"


def test_poll_repo_by_id_enqueues_and_handles_repeated_errors(test_db_session):
    """poll_repo_by_id() es el único punto de entrada real ahora (botón
    "Escanear") -- sigue marcando status="error" tras 5 fallos seguidos,
    igual que hacía antes el barrido periódico."""
    org = create_organization(test_db_session, "Org Scan")
    vcs = VCSConnection(id="vcs-2", org_id=org.id, access_token="token_vcs2")
    test_db_session.add(vcs)

    repo = MonitoredRepo(
        id="repo-scan-1",
        org_id=org.id,
        vcs_connection_id=vcs.id,
        repo_path="owner/scanrepo",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = None

    target_prs = "watchgate.adapters.github_client.GitHubClient.list_all_open_pull_requests"
    target_sess = "watchgate.service.repo_polling.get_session"
    with (
        patch(target_sess, side_effect=lambda: iter([test_db_session])),
        patch("watchgate.dashboard.backend.tasks.get_queue", return_value=mock_queue),
        patch(target_prs) as mock_fetch,
    ):
        mock_fetch.return_value = [{"number": 101}, {"number": 102}]
        enqueued = RepoPollingService.poll_repo_by_id("repo-scan-1")

        assert enqueued == 2
        assert mock_queue.enqueue.call_count == 2

        # Cinco escaneos seguidos fallando -> el repo pasa a status="error".
        mock_fetch.side_effect = Exception("GitHub API Down")
        for _ in range(5):
            RepoPollingService.poll_repo_by_id("repo-scan-1")

        repo_updated = test_db_session.get(MonitoredRepo, "repo-scan-1")
        assert repo_updated.status == "error"
        assert repo_updated.consecutive_errors >= 5


def test_poll_repo_by_id_malformed_repo_path_does_not_raise(test_db_session, monkeypatch):
    """Regresión de un bug real: un repo_path sin '/' (residuo de una
    prueba con un repo git local) hacía que
    `owner, repo_name = repo_path.split("/", 1)` lanzara ValueError SIN
    capturar. Ahora debe: 1) no propagar la excepción, 2) marcarlo como un
    fallo más (mismo camino de consecutive_errors que un fallo de red de
    verdad)."""
    org = create_organization(test_db_session, "Org Malformed")

    malformed = MonitoredRepo(
        id="repo-malformed",
        org_id=org.id,
        repo_path="prueba-1",  # sin "/" -- exactamente el caso reproducido en producción
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(malformed)
    test_db_session.commit()

    monkeypatch.setenv("WATCHGATE_GITHUB_TOKEN", "fake-token")

    target_sess = "watchgate.service.repo_polling.get_session"
    with patch(target_sess, side_effect=lambda: iter([test_db_session])):
        for _ in range(5):
            enqueued = RepoPollingService.poll_repo_by_id("repo-malformed")  # no debe lanzar
            assert enqueued == 0

    malformed_updated = test_db_session.get(MonitoredRepo, "repo-malformed")
    assert malformed_updated.consecutive_errors >= 5
    assert malformed_updated.status == "error"


def test_patch_external_repo_endpoint_and_rbac(test_db_session):
    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user

    user_admin = _get_or_create_db_user(test_db_session, "admin@corp.com")
    user_revisor = _get_or_create_db_user(test_db_session, "revisor@corp.com")
    user_revisor.org_id = user_admin.org_id
    test_db_session.add(user_revisor)
    test_db_session.commit()

    repo = MonitoredRepo(
        id="repo-patch-1",
        org_id=user_admin.org_id,
        repo_path="acme/patchrepo",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    # Configurar sesión en la BD del dashboard para require_role
    from watchgate.dashboard.backend.db import db_session as dash_db_session
    from watchgate.dashboard.backend.db import upsert_role

    with dash_db_session() as dash_conn:
        upsert_role(dash_conn, "admin@corp.com", "acme/patchrepo", "admin_organizacion")
        upsert_role(dash_conn, "revisor@corp.com", "acme/patchrepo", "revisor")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token_admin = create_session_token("admin@corp.com")
    token_revisor = create_session_token("revisor@corp.com")

    # 1. Usuario revisor intenta actualizar -> 403 Forbidden
    client.cookies.set("watchgate_session", token_revisor)
    response = client.patch("/api/repos/external/repo-patch-1", json={"status": "paused"})
    assert response.status_code == 403

    # 2. Usuario admin actualiza con un estado inválido -> 400 Bad Request
    client.cookies.set("watchgate_session", token_admin)
    response = client.patch("/api/repos/external/repo-patch-1", json={"status": "bogus"})
    assert response.status_code == 400

    # 3. Usuario admin actualiza correctamente
    response = client.patch("/api/repos/external/repo-patch-1", json={"status": "paused"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "paused"

    app.dependency_overrides.clear()


def _setup_admin_and_revisor(test_db_session, repo_path):
    from watchgate.dashboard.backend.db import db_session as dash_db_session
    from watchgate.dashboard.backend.db import upsert_role
    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user

    user_admin = _get_or_create_db_user(test_db_session, "admin@corp.com")
    user_revisor = _get_or_create_db_user(test_db_session, "revisor@corp.com")
    user_revisor.org_id = user_admin.org_id
    test_db_session.add(user_revisor)
    test_db_session.commit()

    with dash_db_session() as dash_conn:
        upsert_role(dash_conn, "admin@corp.com", repo_path, "admin_organizacion")
        upsert_role(dash_conn, "revisor@corp.com", repo_path, "revisor")

    return user_admin


def test_delete_external_repo_removes_it_and_keeps_history(test_db_session):
    """El repo desaparece de MonitoredRepo, pero el histórico de análisis
    (tabla `pr_scores` del Dashboard, sin FK hacia monitored_repos) no se
    toca -- decisión explícita del equipo, ver conversación 2026-08-17."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    user_admin = _setup_admin_and_revisor(test_db_session, "acme/deleterepo")
    repo = MonitoredRepo(
        id="repo-delete-1",
        org_id=user_admin.org_id,
        repo_path="acme/deleterepo",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    # Revisor no puede borrar (min_role="mantenedor")
    client.cookies.set("watchgate_session", create_session_token("revisor@corp.com"))
    response = client.delete("/api/repos/external/repo-delete-1")
    assert response.status_code == 403

    # Admin sí puede
    client.cookies.set("watchgate_session", create_session_token("admin@corp.com"))
    response = client.delete("/api/repos/external/repo-delete-1")
    assert response.status_code == 204

    assert test_db_session.get(MonitoredRepo, "repo-delete-1") is None

    app.dependency_overrides.clear()


def test_delete_external_repo_404_for_unknown_repo(test_db_session):
    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db
    _setup_admin_and_revisor(test_db_session, "acme/whatever")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    client.cookies.set("watchgate_session", create_session_token("admin@corp.com"))
    response = client.delete("/api/repos/external/does-not-exist")
    assert response.status_code == 404

    app.dependency_overrides.clear()


def test_delete_external_repo_blocked_when_api_key_bound_to_it(test_db_session):
    """Regresión: `UserAPIKey.monitored_repo_id` tiene FK real hacia
    monitored_repos.id -- borrar el repo sin comprobar esto primero
    dejaría la key con una FK rota (o exigiría poner monitored_repo_id a
    NULL en silencio, degradando su alcance sin que el dueño se entere)."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    user_admin = _setup_admin_and_revisor(test_db_session, "acme/keyedrepo")
    repo = MonitoredRepo(
        id="repo-delete-keyed",
        org_id=user_admin.org_id,
        repo_path="acme/keyedrepo",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.add(
        UserAPIKey(
            id="key-1",
            user_id=user_admin.id,
            org_id=user_admin.org_id,
            monitored_repo_id="repo-delete-keyed",
            name="CI runner",
            key_prefix="wg_live_abcd",
            key_hash="x" * 64,
        )
    )
    test_db_session.commit()

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    client.cookies.set("watchgate_session", create_session_token("admin@corp.com"))
    response = client.delete("/api/repos/external/repo-delete-keyed")
    assert response.status_code == 409
    assert "API key" in response.json()["detail"]
    assert test_db_session.get(MonitoredRepo, "repo-delete-keyed") is not None

    app.dependency_overrides.clear()


def _seed_knowledge_graph(session, monitored_repo_id):
    """Filas del mapa de conocimiento que cuelgan de un `MonitoredRepo` --
    con FK hacia `monitored_repos.id` SIN `ON DELETE CASCADE`."""
    node = RepoGraphNode(
        id=f"node-{monitored_repo_id}",
        monitored_repo_id=monitored_repo_id,
        file_path="src/app.py",
        summary="entrypoint",
        content_hash="abc123",
        loc=10,
    )
    session.add(node)
    session.add(
        RepoGraphEdge(
            id=f"edge-{monitored_repo_id}",
            monitored_repo_id=monitored_repo_id,
            source_node_id=node.id,
            target_node_id=node.id,
        )
    )
    session.add(
        RepoArchitectureSummary(
            id=f"arch-{monitored_repo_id}",
            monitored_repo_id=monitored_repo_id,
            overview="resumen",
            status="ready",
        )
    )
    session.commit()


def _assert_knowledge_graph_gone(session, monitored_repo_id):
    from sqlmodel import select as _select

    for model in (RepoGraphEdge, RepoGraphNode, RepoArchitectureSummary):
        left = session.exec(
            _select(model).where(model.monitored_repo_id == monitored_repo_id)
        ).all()
        assert left == [], f"{model.__name__} huérfano tras borrar el repo: {left}"


def test_delete_external_repo_also_wipes_knowledge_graph(test_db_session):
    """Regresión: `repo_graph_nodes`/`repo_graph_edges`/
    `repo_architecture_summaries` tienen FK hacia `monitored_repos.id` sin
    `ON DELETE CASCADE`. Borrar el repo sin limpiarlas antes revienta con
    un `ForeignKeyViolation` (500 opaco en el Dashboard) en Postgres, y
    deja filas huérfanas en SQLite."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    user_admin = _setup_admin_and_revisor(test_db_session, "acme/kgrepo")
    test_db_session.add(
        MonitoredRepo(
            id="repo-kg-1",
            org_id=user_admin.org_id,
            repo_path="acme/kgrepo",
            monitor_type="audited",
            status="active",
        )
    )
    test_db_session.commit()
    _seed_knowledge_graph(test_db_session, "repo-kg-1")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    client.cookies.set("watchgate_session", create_session_token("admin@corp.com"))
    response = client.delete("/api/repos/external/repo-kg-1")
    assert response.status_code == 204, response.text

    assert test_db_session.get(MonitoredRepo, "repo-kg-1") is None
    _assert_knowledge_graph_gone(test_db_session, "repo-kg-1")

    app.dependency_overrides.clear()


def test_delete_repo_by_path_wipes_monitored_repo_and_knowledge_graph(test_db_session):
    """`DELETE /api/repos/{repo}` (borrado por path, borra también el
    histórico de scores): mismo barrido de las filas del mapa de
    conocimiento que `delete_external_repo`."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    user_admin = _setup_admin_and_revisor(test_db_session, "acme/kgpath")
    test_db_session.add(
        MonitoredRepo(
            id="repo-kg-path",
            org_id=user_admin.org_id,
            repo_path="acme/kgpath",
            monitor_type="audited",
            status="active",
        )
    )
    test_db_session.commit()
    _seed_knowledge_graph(test_db_session, "repo-kg-path")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    client.cookies.set("watchgate_session", create_session_token("admin@corp.com"))
    response = client.delete("/api/repos/acme/kgpath")
    assert response.status_code == 200, response.text
    assert response.json()["monitored_repo_deleted"] is True

    assert test_db_session.get(MonitoredRepo, "repo-kg-path") is None
    _assert_knowledge_graph_gone(test_db_session, "repo-kg-path")

    app.dependency_overrides.clear()


def test_delete_repo_by_path_keeps_history_when_api_key_bound(test_db_session):
    """El 409 por API key atada va ANTES de borrar el histórico de scores
    -- antes se borraba primero y quedabas con el histórico perdido y aun
    así un error, estado partido irreversible."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    user_admin = _setup_admin_and_revisor(test_db_session, "acme/kgkeyed")
    test_db_session.add(
        MonitoredRepo(
            id="repo-kg-keyed",
            org_id=user_admin.org_id,
            repo_path="acme/kgkeyed",
            monitor_type="audited",
            status="active",
        )
    )
    test_db_session.add(
        UserAPIKey(
            id="key-kg-1",
            user_id=user_admin.id,
            org_id=user_admin.org_id,
            monitored_repo_id="repo-kg-keyed",
            name="CI runner",
            key_prefix="wg_live_abcd",
            key_hash="x" * 64,
        )
    )
    test_db_session.commit()

    from watchgate.dashboard.backend.db import db_session as dash_db_session

    with dash_db_session() as dash_conn:
        from watchgate.core.models import AggregatedResult, LayerResult, Semaforo

        layers = {
            n: LayerResult(layer_name=n, risk_score=10, justification="", skipped=False)
            for n in ("static", "deps", "reputation", "semantic")
        }
        from watchgate.dashboard.backend import db as dash_db

        dash_db.insert_aggregated(
            dash_conn,
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
                pr_id="7",
                repo="acme/kgkeyed",
                timestamp="2026-08-01T12:00:00+00:00",
            ),
        )

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    client.cookies.set("watchgate_session", create_session_token("admin@corp.com"))
    response = client.delete("/api/repos/acme/kgkeyed")
    assert response.status_code == 409
    assert "API key" in response.json()["detail"]

    assert test_db_session.get(MonitoredRepo, "repo-kg-keyed") is not None
    with dash_db_session() as dash_conn:
        from watchgate.dashboard.backend import db as dash_db

        assert dash_db.list_scores(dash_conn, "acme/kgkeyed") != []

    app.dependency_overrides.clear()


def test_add_external_repo_triggers_instant_poll(test_db_session):
    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user

    _get_or_create_db_user(test_db_session, "creator@corp.com")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator@corp.com")
    client.cookies.set("watchgate_session", token)

    target_poll = "watchgate.service.repo_polling.RepoPollingService.poll_repo_by_id"
    target_queue = "watchgate.dashboard.backend.routers.repos.get_queue"
    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = None
    with patch(target_poll) as mock_poll, patch(target_queue, return_value=mock_queue):
        response = client.post(
            "/api/repos/external",
            json={"repo_path": "openclaw/instantrepo", "monitor_type": "audited"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["repo_path"] == "openclaw/instantrepo"
        assert mock_poll.called
        assert mock_poll.call_args[0][0] == data["id"]

    app.dependency_overrides.clear()


def test_add_external_repo_audited_enqueues_main_branch_scan(test_db_session):
    """Al dar de alta un repo "audited" (auditoría externa), debe encolarse
    también run_main_branch_scan -- el escaneo de línea base de TODO el
    contenido actual de la rama por defecto, no solo de sus PRs futuras."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
    from watchgate.dashboard.backend.tasks import run_main_branch_scan

    creator = _get_or_create_db_user(test_db_session, "creator2@corp.com")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator2@corp.com")
    client.cookies.set("watchgate_session", token)

    target_poll = "watchgate.service.repo_polling.RepoPollingService.poll_repo_by_id"
    target_queue = "watchgate.dashboard.backend.routers.repos.get_queue"
    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = None
    with patch(target_poll), patch(target_queue, return_value=mock_queue):
        response = client.post(
            "/api/repos/external",
            json={"repo_path": "openclaw/baselinerepo", "monitor_type": "audited"},
        )
        assert response.status_code == 201

    main_branch_calls = [
        call for call in mock_queue.enqueue.call_args_list if call.args[0] is run_main_branch_scan
    ]
    assert len(main_branch_calls) == 1
    call = main_branch_calls[0]
    assert call.args[1] == "openclaw/baselinerepo"  # repo_path
    assert call.args[2] == creator.org_id  # org_id
    assert call.args[3] is None  # vcs_connection_id (no se pasó ninguno)
    # job_id incluye org_id -- dos orgs distintas pueden auditar el mismo
    # repo_path sin colisionar entre sí (ver comentario en repos.py). '-'
    # como separador (no ':') porque RQ valida el job_id contra
    # [A-Za-z0-9_-]+ -- ver test_safe_job_id_part_* más abajo.
    assert call.kwargs["job_id"] == f"main_branch_scan-{creator.org_id}-openclaw_baselinerepo"

    app.dependency_overrides.clear()


def test_add_external_repo_deletes_stale_failed_main_branch_scan_job_before_reenqueueing(
    test_db_session,
):
    """Regresión de un bug real reproducido en vivo: si ya existe en Redis
    un job con ese job_id en estado failed (p. ej. de un intento anterior
    para el mismo repo_path), volver a llamar a queue.enqueue() con el
    MISMO job_id actualiza sus datos pero NO lo vuelve a meter en la lista
    de la cola -- ningún worker lo recoge nunca, se queda "atascado" en
    silencio. Hay que borrar el job viejo explícitamente antes de
    reencolar (mismo patrón que RepoPollingService._poll_single_candidate)."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
    from watchgate.dashboard.backend.tasks import run_main_branch_scan

    creator = _get_or_create_db_user(test_db_session, "creator4@corp.com")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator4@corp.com")
    client.cookies.set("watchgate_session", token)

    stale_failed_job = MagicMock()
    stale_failed_job.is_failed = True

    target_poll = "watchgate.service.repo_polling.RepoPollingService.poll_repo_by_id"
    target_queue = "watchgate.dashboard.backend.routers.repos.get_queue"
    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = stale_failed_job
    with patch(target_poll), patch(target_queue, return_value=mock_queue):
        response = client.post(
            "/api/repos/external",
            json={"repo_path": "openclaw/staleretry", "monitor_type": "audited"},
        )
        assert response.status_code == 201

    # El job viejo (failed) se borra explícitamente...
    assert stale_failed_job.delete.called
    # ...y SÍ se vuelve a encolar uno nuevo con el mismo job_id.
    main_branch_calls = [
        call for call in mock_queue.enqueue.call_args_list if call.args[0] is run_main_branch_scan
    ]
    assert len(main_branch_calls) == 1
    expected_job_id = f"main_branch_scan-{creator.org_id}-openclaw_staleretry"
    assert main_branch_calls[0].kwargs["job_id"] == expected_job_id

    app.dependency_overrides.clear()


def test_safe_job_id_part_produces_ids_that_real_rq_accepts():
    """Bug real, reproducido en vivo (500 en POST /api/repos/external y en
    POST /repos/external/{id}/scan-main): RQ valida `job_id` contra
    `[A-Za-z0-9_-]+` (`rq.job.JOB_ID_PATTERN`, estable entre versiones --
    no se importa la función interna de validación aquí porque el venv
    local de desarrollo tiene rq==1.16.2 desincronizado del `rq>=2.11,<3.0`
    real de pyproject.toml/el contenedor, donde sí se reprodujo el bug en
    vivo) -- un `repo_path` real como "owner/repo" (barra) o
    "usuario/Curso.Prep.Henry" (punto) lo revienta con `ValueError: Job ID
    must only contain letters, numbers, underscores and dashes`. Los tests
    de arriba mockean `get_queue()` entero, así que nunca ejercitan la
    validación REAL de RQ -- por eso este bug no se detectó antes."""
    import re

    from watchgate.dashboard.backend.routers.repos import _safe_job_id_part

    real_world_repo_paths = [
        "owner/repo",
        "marjosavi481/Curso.Prep.Henry",
        "a/b/c",
        "repo con espacios",
        "répo-ñ",
    ]
    for repo_path in real_world_repo_paths:
        job_id = f"main_branch_scan-{_safe_job_id_part('org-123')}-{_safe_job_id_part(repo_path)}"
        assert re.fullmatch(r"[A-Za-z0-9_-]+", job_id), job_id


def test_poll_single_candidate_audit_pr_job_id_survives_real_rq_validation():
    """MISMO bug que el test anterior, pero en `_poll_single_candidate`
    (`watchgate/service/repo_polling.py`) -- tenía su PROPIO `job_id`
    (`f"audit_pr:{repo_path}:{pr_num}"`, con ':' como separador) sin pasar
    por `safe_job_id_part`, así que seguía roto aunque el de
    `_enqueue_main_branch_scan` ya estuviera arreglado. Reproducido en vivo
    contra PRs reales abiertas de un repo de GitHub: CUALQUIER repo
    "audited" con al menos una PR abierta nueva hacía fallar tanto el
    escaneo automático al conectar el repo como el botón "Escanear", sin
    encolar ninguna PR -- justo el síntoma reportado ("no analiza las
    últimas pull request automáticamente"). `test_poll_repo_by_id_enqueues_
    and_handles_repeated_errors` de arriba mockea `get_queue()` entero, así
    que nunca ejercitó la validación real de RQ."""
    import re

    from watchgate.service.repo_polling import safe_job_id_part

    real_world_repo_paths = ["owner/repo", "pablojimz/watch_gate", "usuario/Curso.Prep.Henry"]
    for repo_path in real_world_repo_paths:
        for pr_num in (33, 101):
            job_id = f"audit_pr-{safe_job_id_part(repo_path)}-{pr_num}"
            assert re.fullmatch(r"[A-Za-z0-9_-]+", job_id), job_id


def test_add_external_repo_skips_main_branch_scan_when_job_already_in_flight(test_db_session):
    """Lo contrario del test de arriba: si el job existente NO está failed
    (sigue en cola o corriendo), no hay que tocarlo ni volver a encolar --
    solo el caso failed necesita limpieza."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
    from watchgate.dashboard.backend.tasks import run_main_branch_scan

    _get_or_create_db_user(test_db_session, "creator5@corp.com")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator5@corp.com")
    client.cookies.set("watchgate_session", token)

    in_flight_job = MagicMock()
    in_flight_job.is_failed = False

    target_poll = "watchgate.service.repo_polling.RepoPollingService.poll_repo_by_id"
    target_queue = "watchgate.dashboard.backend.routers.repos.get_queue"
    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = in_flight_job
    with patch(target_poll), patch(target_queue, return_value=mock_queue):
        response = client.post(
            "/api/repos/external",
            json={"repo_path": "openclaw/inflight", "monitor_type": "audited"},
        )
        assert response.status_code == 201

    assert not in_flight_job.delete.called
    main_branch_calls = [
        call for call in mock_queue.enqueue.call_args_list if call.args[0] is run_main_branch_scan
    ]
    assert main_branch_calls == []

    app.dependency_overrides.clear()


def test_add_external_repo_managed_also_enqueues_main_branch_scan(test_db_session):
    """El escaneo de línea base se dispara para CUALQUIER tipo de repo al
    conectarse -- antes solo pasaba para "audited"; un repo "managed"
    (GitHub App con permisos reales, vía webhook) se quedaba sin foto de
    riesgo inicial pese a tener permisos de sobra para escanearlo. Mismo
    criterio que "audited": evento único de onboarding, no repolling."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
    from watchgate.dashboard.backend.tasks import run_main_branch_scan

    creator = _get_or_create_db_user(test_db_session, "creator3@corp.com")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator3@corp.com")
    client.cookies.set("watchgate_session", token)

    target_poll = "watchgate.service.repo_polling.RepoPollingService.poll_repo_by_id"
    target_queue = "watchgate.dashboard.backend.routers.repos.get_queue"
    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = None
    with patch(target_poll) as mock_poll, patch(target_queue, return_value=mock_queue):
        response = client.post(
            "/api/repos/external",
            json={"repo_path": "openclaw/managedrepo", "monitor_type": "managed"},
        )
        assert response.status_code == 201

    # Las PRs abiertas ya existentes también se escanean, igual que en
    # "audited" -- poll_repo_by_id no distingue por monitor_type.
    assert mock_poll.called

    main_branch_calls = [
        call for call in mock_queue.enqueue.call_args_list if call.args[0] is run_main_branch_scan
    ]
    assert len(main_branch_calls) == 1
    assert main_branch_calls[0].args[1] == "openclaw/managedrepo"
    assert (
        main_branch_calls[0].kwargs["job_id"]
        == f"main_branch_scan-{creator.org_id}-openclaw_managedrepo"
    )

    app.dependency_overrides.clear()


def test_scan_main_branch_endpoint_enqueues_job(test_db_session):
    """Botón "Escanear rama principal": POST /{repo_id}/scan-main encola
    run_main_branch_scan bajo demanda, con independencia de si el repo ya
    tuvo su escaneo de línea base al conectarse."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
    from watchgate.dashboard.backend.tasks import run_main_branch_scan

    creator = _get_or_create_db_user(test_db_session, "creator6@corp.com")
    repo = MonitoredRepo(
        id="repo-scan-main",
        org_id=creator.org_id,
        repo_path="openclaw/scanmainrepo",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator6@corp.com")
    client.cookies.set("watchgate_session", token)

    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = None
    target_queue = "watchgate.dashboard.backend.routers.repos.get_queue"
    with patch(target_queue, return_value=mock_queue):
        response = client.post("/api/repos/external/repo-scan-main/scan-main")

    assert response.status_code == 202
    data = response.json()
    assert data["enqueued"] is True
    assert data["repo_path"] == "openclaw/scanmainrepo"

    main_branch_calls = [
        call for call in mock_queue.enqueue.call_args_list if call.args[0] is run_main_branch_scan
    ]
    assert len(main_branch_calls) == 1
    assert main_branch_calls[0].args[1] == "openclaw/scanmainrepo"
    assert main_branch_calls[0].args[2] == creator.org_id

    app.dependency_overrides.clear()


def test_scan_main_branch_endpoint_skips_when_job_already_in_flight(test_db_session):
    """No duplica trabajo: si ya hay un escaneo de rama principal en curso
    (ni failed ni terminado) para este repo, no vuelve a encolar."""

    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
    from watchgate.dashboard.backend.tasks import run_main_branch_scan

    creator = _get_or_create_db_user(test_db_session, "creator7@corp.com")
    repo = MonitoredRepo(
        id="repo-scan-main-2",
        org_id=creator.org_id,
        repo_path="openclaw/inflightmain",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator7@corp.com")
    client.cookies.set("watchgate_session", token)

    in_flight_job = MagicMock()
    in_flight_job.is_failed = False
    mock_queue = MagicMock()
    mock_queue.fetch_job.return_value = in_flight_job
    target_queue = "watchgate.dashboard.backend.routers.repos.get_queue"
    with patch(target_queue, return_value=mock_queue):
        response = client.post("/api/repos/external/repo-scan-main-2/scan-main")

    assert response.status_code == 202
    assert response.json()["enqueued"] is False
    assert not in_flight_job.delete.called
    main_branch_calls = [
        call for call in mock_queue.enqueue.call_args_list if call.args[0] is run_main_branch_scan
    ]
    assert main_branch_calls == []

    app.dependency_overrides.clear()


def test_scan_main_branch_endpoint_404_for_unknown_repo(test_db_session):
    def get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = get_test_db

    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user

    _get_or_create_db_user(test_db_session, "creator8@corp.com")

    client = TestClient(app)
    from watchgate.dashboard.backend.auth import create_session_token

    token = create_session_token("creator8@corp.com")
    client.cookies.set("watchgate_session", token)

    response = client.post("/api/repos/external/no-existe/scan-main")
    assert response.status_code == 404

    app.dependency_overrides.clear()
