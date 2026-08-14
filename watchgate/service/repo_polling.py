"""Servicio de polling de repositorios externos (Clean Architecture & SRP)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select

from watchgate.adapters.github_client import GitHubClient
from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo, PRScore, VCSConnection


class RepoPollingService:
    @staticmethod
    def get_candidate_repos() -> list[dict[str, Any]]:
        """Obtiene la lista de repositorios candidatos cerrando la sesión de DB inmediatamente."""
        now = datetime.now(UTC)
        candidates: list[dict[str, Any]] = []
        default_token = os.environ.get("WATCHGATE_GITHUB_TOKEN")

        with next(get_session()) as session:
            repos = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.monitor_type == "audited",
                    MonitoredRepo.status == "active",
                    MonitoredRepo.auto_scan_prs == True,  # noqa: E712
                )
            ).all()

            for repo in repos:
                if repo.last_polled_at:
                    elapsed = (
                        now - repo.last_polled_at.replace(tzinfo=UTC)
                    ).total_seconds() / 60.0
                    if elapsed < repo.scan_interval_minutes:
                        continue

                # Token específico o token global del sistema
                token = default_token
                if repo.vcs_connection_id:
                    vcs = session.exec(
                        select(VCSConnection).where(VCSConnection.id == repo.vcs_connection_id)
                    ).first()
                    if vcs and vcs.access_token:
                        token = vcs.access_token

                # Si no hay token disponible, omitir para no agotar la cuota por IP pública
                if not token:
                    continue

                candidates.append(
                    {
                        "id": repo.id,
                        "repo_path": repo.repo_path,
                        "org_id": repo.org_id,
                        "vcs_connection_id": repo.vcs_connection_id,
                        "prs_etag": repo.prs_etag,
                        "token": token,
                    }
                )

        return candidates

    @classmethod
    def poll_all_candidates(cls) -> int:
        """Efectúa el barrido con llamadas HTTP sin bloqueo de transacciones DB."""
        candidates = cls.get_candidate_repos()
        total_enqueued = 0
        now = datetime.now(UTC)

        for candidate in candidates:
            owner, repo_name = candidate["repo_path"].split("/", 1)
            client = GitHubClient(candidate["token"])

            try:
                prs, new_etag = client.list_recent_pull_requests_with_etag(
                    owner, repo_name, per_page=10, etag=candidate["prs_etag"]
                )
                success = True
            except Exception:
                prs, new_etag = None, None
                success = False

            # Actualizar estado HTTP y contador de errores en la BD
            with next(get_session()) as session:
                repo_db = session.get(MonitoredRepo, candidate["id"])
                if repo_db:
                    repo_db.last_polled_at = now
                    if success:
                        repo_db.consecutive_errors = 0
                        if new_etag:
                            repo_db.prs_etag = new_etag
                    else:
                        repo_db.consecutive_errors += 1
                        if repo_db.consecutive_errors >= 5:
                            repo_db.status = "error"
                    session.commit()

            if not success or prs is None:
                # Fallo o HTTP 304 Not Modified
                continue

            # Consultar PRs analizadas previamente con SQLModel
            with next(get_session()) as session:
                analyzed_pr_ids = set(
                    session.exec(
                        select(PRScore.pr_id).where(PRScore.repo == candidate["repo_path"])
                    ).all()
                )

            # Filtrar PRs nuevas
            new_prs = [p for p in prs if str(p["number"]) not in analyzed_pr_ids]

            from watchgate.dashboard.backend.tasks import get_queue, run_audit_scan

            queue = get_queue()

            for pr in new_prs[:5]:
                pr_num = int(pr["number"])
                job_id = f"audit_pr:{candidate['repo_path']}:{pr_num}"

                existing_job = queue.fetch_job(job_id)
                if existing_job:
                    if existing_job.is_failed:
                        existing_job.delete()  # Limpiar job fallido para permitir reintento
                    else:
                        continue

                queue.enqueue(
                    run_audit_scan,
                    candidate["repo_path"],
                    pr_num,
                    candidate["org_id"],
                    candidate["vcs_connection_id"],
                    job_id=job_id,
                )
                total_enqueued += 1

        return total_enqueued
