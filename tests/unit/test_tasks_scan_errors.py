"""Tests unitarios para el manejo de errores de las tareas de escaneo
(`run_audit_scan`/`run_managed_scan`/`run_main_branch_scan` en
`dashboard/backend/tasks.py`).

Antes de este fix, ninguna de las tres tenía un solo `try/except` alrededor
del cuerpo principal: si `GitHubClient` o `QuotaService.analyze_with_quota`
lanzaban (token inválido, PR inexistente, fallo de red...), la excepción se
propagaba sin más -- no quedaba reflejada en `MonitoredRepo`
(`consecutive_errors`/`status`), no había log de aplicación, y el usuario no
tenía forma de enterarse (ver `.claude/informe-puerta-2.md`). Estos tests
cubren justo ese hueco -- antes, ni siquiera existía `tests/unit/test_tasks.py`.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session

os.environ["WATCHGATE_DB_SECRET"] = "1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I="
import watchgate.db.crypto  # noqa: E402

watchgate.db.crypto._fernet = Fernet("1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=")

from watchgate.dashboard.backend import tasks  # noqa: E402
from watchgate.db.connection import build_engine  # noqa: E402
from watchgate.db.models import MonitoredRepo, VCSConnection  # noqa: E402
from watchgate.db.repository import create_organization  # noqa: E402


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_tasks_scan_errors.db"
    test_engine = build_engine(f"sqlite:///{db_file}")

    from watchgate.db.connection import SQLModel

    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        yield session


def _patched_sessions(test_db_session):
    """Mismo patrón que `test_repos_scan.py`: parchea `get_session` en cada
    módulo que lo importó por su cuenta (`tasks.py` y `repo_polling.py`
    tienen cada uno su propio nombre local `get_session`) para que ambos
    reutilicen la sesión de test SQLite en vez de abrir Postgres."""
    return (
        patch(
            "watchgate.dashboard.backend.tasks.get_session",
            side_effect=lambda: iter([test_db_session]),
        ),
        patch(
            "watchgate.service.repo_polling.get_session",
            side_effect=lambda: iter([test_db_session]),
        ),
    )


def test_run_audit_scan_failure_marks_repo_error_and_reraises(test_db_session):
    """Camino de fallo de `run_audit_scan`: un error de GitHub (token
    inválido, PR borrada, fallo de red...) debe 1) seguir relanzándose (RQ
    tiene que poder marcar el job como failed) y 2) reflejarse en
    `MonitoredRepo.consecutive_errors`/`status` tras 5 fallos seguidos --
    mismo criterio que ya usaba el fallo al listar PRs abiertas."""
    org = create_organization(test_db_session, "Org Audit Fail")
    org_id = org.id  # capturado ANTES del bucle: cada llamada a
    # run_audit_scan cierra (y por tanto expulsa los objetos de) la misma
    # sesión de test reutilizada -- volver a leer `org.id` tras la primera
    # iteración fallaría con "Instance not bound to a Session".
    repo = MonitoredRepo(
        id="repo-audit-fail",
        org_id=org_id,
        repo_path="owner/repo",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    sess_patch, poll_sess_patch = _patched_sessions(test_db_session)
    with (
        sess_patch,
        poll_sess_patch,
        patch("watchgate.dashboard.backend.tasks.GitHubClient") as MockClient,
    ):
        MockClient.return_value.get_pull_request_data.side_effect = Exception("GitHub API caída")

        for _ in range(5):
            with pytest.raises(Exception, match="GitHub API caída"):
                tasks.run_audit_scan(
                    "owner/repo",
                    1,
                    org_id,
                    None,
                    github_token="t",
                    github_api_url="https://api.github.com",
                )

    updated = test_db_session.get(MonitoredRepo, "repo-audit-fail")
    assert updated.consecutive_errors >= 5
    assert updated.status == "error"
    assert updated.last_scanned_at is None  # nunca llegó a completar con éxito


def test_run_main_branch_scan_failure_marks_repo_error_and_reraises(test_db_session):
    """Mismo caso que arriba pero para el escaneo de línea base."""
    org = create_organization(test_db_session, "Org Main Branch Fail")
    org_id = org.id  # ver comentario equivalente en el test de arriba
    repo = MonitoredRepo(
        id="repo-main-fail",
        org_id=org_id,
        repo_path="owner/repo2",
        monitor_type="audited",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    sess_patch, poll_sess_patch = _patched_sessions(test_db_session)
    with (
        sess_patch,
        poll_sess_patch,
        patch("watchgate.dashboard.backend.tasks.GitHubClient") as MockClient,
    ):
        MockClient.return_value.get_default_branch_scan_data.side_effect = Exception(
            "PR/rama inexistente"
        )

        for _ in range(5):
            with pytest.raises(Exception, match="PR/rama inexistente"):
                tasks.run_main_branch_scan(
                    "owner/repo2",
                    org_id,
                    None,
                    github_token="t",
                    github_api_url="https://api.github.com",
                )

    updated = test_db_session.get(MonitoredRepo, "repo-main-fail")
    assert updated.consecutive_errors >= 5
    assert updated.status == "error"
    assert updated.last_scanned_at is None


def test_run_managed_scan_failure_marks_repo_error_and_reraises(test_db_session):
    """`run_managed_scan` (webhook de repos "managed") tenía el mismo
    hueco -- un fallo de GitHub durante el análisis tampoco quedaba
    reflejado en el `MonitoredRepo` asociado a esa instalación."""
    org = create_organization(test_db_session, "Org Managed Fail")
    vcs = VCSConnection(id="vcs-managed-fail", org_id=org.id, installation_id="inst-1")
    test_db_session.add(vcs)
    repo = MonitoredRepo(
        id="repo-managed-fail",
        org_id=org.id,
        vcs_connection_id=vcs.id,
        repo_path="owner/repo3",
        monitor_type="managed",
        status="active",
    )
    test_db_session.add(repo)
    test_db_session.commit()

    sess_patch, poll_sess_patch = _patched_sessions(test_db_session)
    with (
        sess_patch,
        poll_sess_patch,
        patch("watchgate.dashboard.backend.tasks.GitHubClient") as MockClient,
    ):
        MockClient.return_value.get_pull_request_data.side_effect = Exception("Rate limit excedido")

        for _ in range(5):
            with pytest.raises(Exception, match="Rate limit excedido"):
                tasks.run_managed_scan(
                    "owner/repo3",
                    7,
                    "inst-1",
                    github_token="t",
                    github_api_url="https://api.github.com",
                )

    updated = test_db_session.get(MonitoredRepo, "repo-managed-fail")
    assert updated.consecutive_errors >= 5
    assert updated.status == "error"


def test_run_managed_scan_post_comment_failure_does_not_mark_repo_as_failed(test_db_session):
    """Distinción deliberada: si el análisis se guarda bien pero solo falla
    la publicación del comentario en GitHub (p. ej. el token no tiene
    permiso de escritura), el repo NO debe marcarse como si el escaneo
    hubiera fallado -- el dato ya está guardado, es un fallo best-effort
    aparte. `run_managed_scan` no debe relanzar en este caso."""
    org = create_organization(test_db_session, "Org Comment Fail", monthly_token_quota=100_000)
    vcs = VCSConnection(id="vcs-comment-fail", org_id=org.id, installation_id="inst-2")
    test_db_session.add(vcs)
    repo = MonitoredRepo(
        id="repo-comment-fail",
        org_id=org.id,
        vcs_connection_id=vcs.id,
        repo_path="owner/repo4",
        monitor_type="managed",
        status="active",
        consecutive_errors=3,  # simula una racha previa que el ÉXITO debe limpiar
    )
    test_db_session.add(repo)
    test_db_session.commit()

    sess_patch, poll_sess_patch = _patched_sessions(test_db_session)
    with (
        sess_patch,
        poll_sess_patch,
        patch("watchgate.dashboard.backend.tasks.GitHubClient") as MockClient,
        patch("watchgate.dashboard.backend.db.insert_aggregated", return_value="score-id"),
        patch("watchgate.dashboard.backend.db.upsert_role"),
        patch("watchgate.dashboard.backend.db.db_session") as mock_dash_session,
    ):
        mock_dash_session.return_value.__enter__.return_value = MagicMock()
        MockClient.return_value.get_pull_request_data.return_value = (
            "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-print('hi')\n+print('bye')",
            {"user": {"login": "octocat"}},
        )
        MockClient.return_value.post_comment.side_effect = Exception(
            "403: token sin permiso de escritura"
        )

        tasks.run_managed_scan(
            "owner/repo4",
            9,
            "inst-2",
            github_token="t",
            github_api_url="https://api.github.com",
        )  # no debe lanzar

    updated = test_db_session.get(MonitoredRepo, "repo-comment-fail")
    assert updated.last_scanned_at is not None
    assert updated.consecutive_errors == 0
    assert updated.status == "active"
