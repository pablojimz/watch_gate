"""Configuración de colas y definición de tareas asíncronas."""

from __future__ import annotations

import os

import redis
from rq import Queue
from sqlmodel import select

from watchgate.adapters.github_client import GitHubClient
from watchgate.config import load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import CommitAuthor
from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo, VCSConnection
from watchgate.service.quota import QuotaService


def run_managed_scan(repo_path: str, pr_number: int, installation_id: str) -> None:
    """Tarea principal para repositorios gestionados vía webhook."""
    with next(get_session()) as session:
        # Buscar la conexión y org a partir de installation_id
        vcs = session.exec(
            select(VCSConnection).where(VCSConnection.installation_id == installation_id)
        ).first()
        if not vcs or not vcs.org_id:
            return  # No registrado

        org_id = vcs.org_id

        # Descargar Diff y Metadata
        token = vcs.access_token if vcs.access_token else None
        client = GitHubClient(token)
        owner, repo_name = repo_path.split("/", 1)

        diff_text, metadata = client.get_pull_request_data(owner, repo_name, pr_number)

        # Construir autores
        author_login = metadata.get("user", {}).get("login", "unknown")
        author = CommitAuthor(name=author_login, email="unknown@example.com", login=author_login)
        parsed_diff = parse_diff_from_text(diff_text, authors=[author])

        # Análisis con control de cuota
        pipeline_metadata: dict[str, object] = {
            "pr_id": str(pr_number),
            "repo": repo_path,
            "author_login": author_login,
        }
        config = load_config()

        quota_service = QuotaService(session)
        result, is_degraded = quota_service.analyze_with_quota(
            diff=parsed_diff,
            metadata=pipeline_metadata,
            config=config,
            org_id=org_id,
            user_id=None,
            agent_id=None,
        )

        # 5. Insertar en la BD del Dashboard para que se pueda visualizar
        from watchgate.dashboard.backend.db import db_session as dashboard_db_session
        from watchgate.dashboard.backend.db import insert_aggregated, upsert_role
        with dashboard_db_session() as dash_conn:
            result.pr_id = str(pr_number)
            result.repo = repo_path
            insert_aggregated(dash_conn, result, author_login=author_login)
            
            # Buscamos el usuario de la DB SQLModel asociado para darle permisos en el esquema del Dashboard
            from watchgate.db.models import User
            user_obj = session.exec(select(User).where(User.org_id == org_id)).first()
            if user_obj:
                upsert_role(dash_conn, user_obj.name, repo_path, "admin_organizacion")

        # Actualizar last_scanned_at
        repo_obj = session.exec(
            select(MonitoredRepo).where(
                MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path
            )
        ).first()
        if repo_obj:
            from datetime import UTC, datetime

            repo_obj.last_scanned_at = datetime.now(UTC)

        session.commit()

        # En managed mode, publicamos un comentario en GitHub (solo si no estamos fallando)
        from watchgate.core.comment_template import render_comment

        comment_body = render_comment(result)
        client.post_comment(owner, repo_name, pr_number, comment_body)


_REDIS_URL = os.environ.get("WATCHGATE_REDIS_URL", "redis://localhost:6379/0")


def get_redis_conn() -> redis.Redis:
    return redis.from_url(_REDIS_URL)


def get_queue() -> Queue:
    return Queue(connection=get_redis_conn())


def run_audit_scan(
    repo_path: str, pr_number: int, org_id: str, vcs_connection_id: str | None
) -> None:
    """Tarea principal de auditoría ejecutada por el worker."""
    with next(get_session()) as session:
        # 1. Obtener token si existe
        token = None
        if vcs_connection_id:
            vcs = session.exec(
                select(VCSConnection).where(VCSConnection.id == vcs_connection_id)
            ).first()
            if vcs and vcs.access_token:
                token = vcs.access_token  # Ya está descifrado gracias a EncryptedString

        # 2. Descargar Diff y Metadata
        client = GitHubClient(token)
        owner, repo_name = repo_path.split("/", 1)

        diff_text, metadata = client.get_pull_request_data(owner, repo_name, pr_number)

        # 3. Construir autores
        author_login = metadata.get("user", {}).get("login", "unknown")
        author = CommitAuthor(name=author_login, email="unknown@example.com", login=author_login)
        parsed_diff = parse_diff_from_text(diff_text, authors=[author])

        # 4. Análisis con control de cuota
        pipeline_metadata: dict[str, object] = {
            "pr_id": str(pr_number),
            "repo": repo_path,
            "author_login": author_login,
        }
        config = load_config()

        quota_service = QuotaService(session)
        # analyze_with_quota calls run_full_analysis and save_pr_score atomically
        result, is_degraded = quota_service.analyze_with_quota(
            diff=parsed_diff,
            metadata=pipeline_metadata,
            config=config,
            org_id=org_id,
            user_id=None,
            agent_id=None,
        )

        # 5. Insertar en la BD del Dashboard para que se pueda visualizar
        from watchgate.dashboard.backend.db import db_session as dashboard_db_session
        from watchgate.dashboard.backend.db import insert_aggregated, upsert_role
        with dashboard_db_session() as dash_conn:
            result.pr_id = str(pr_number)
            result.repo = repo_path
            insert_aggregated(dash_conn, result, author_login=author_login)
            
            # Buscamos el usuario de la DB SQLModel asociado para darle permisos en el esquema del Dashboard
            from watchgate.db.models import User
            user_obj = session.exec(select(User).where(User.org_id == org_id)).first()
            if user_obj:
                upsert_role(dash_conn, user_obj.name, repo_path, "admin_organizacion")

        # Actualizar last_scanned_at
        repo_obj = session.exec(
            select(MonitoredRepo).where(
                MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path
            )
        ).first()
        if repo_obj:
            from datetime import UTC, datetime

            repo_obj.last_scanned_at = datetime.now(UTC)

        session.commit()
