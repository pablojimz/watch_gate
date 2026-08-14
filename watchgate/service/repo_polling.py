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
    def _build_candidate_dict(
        repo: MonitoredRepo, default_token: str | None, session: Any
    ) -> dict[str, Any]:
        token = default_token
        if repo.vcs_connection_id:
            vcs = session.exec(
                select(VCSConnection).where(VCSConnection.id == repo.vcs_connection_id)
            ).first()
            if vcs and vcs.access_token:
                token = vcs.access_token

        return {
            "id": repo.id,
            "repo_path": repo.repo_path,
            "org_id": repo.org_id,
            "vcs_connection_id": repo.vcs_connection_id,
            "prs_etag": repo.prs_etag,
            "token": token,
        }

    @classmethod
    def get_candidate_repos(cls, ignore_interval: bool = False) -> list[dict[str, Any]]:
        """Obtiene la lista de repositorios candidatos cerrando la sesión de DB inmediatamente."""
        now = datetime.now(UTC)
        candidates: list[dict[str, Any]] = []
        default_token = os.environ.get("WATCHGATE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

        with next(get_session()) as session:
            repos = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.status == "active",
                    MonitoredRepo.auto_scan_prs == True,  # noqa: E712
                )
            ).all()

            for repo in repos:
                if not ignore_interval and repo.last_polled_at:
                    elapsed = (now - repo.last_polled_at.replace(tzinfo=UTC)).total_seconds() / 60.0
                    if elapsed < repo.scan_interval_minutes:
                        continue

                cand = cls._build_candidate_dict(repo, default_token, session)
                candidates.append(cand)

        return candidates

    @classmethod
    def get_candidate_repo_by_id(
        cls, repo_id: str, ignore_interval: bool = True
    ) -> dict[str, Any] | None:
        """Obtiene un único candidato por ID para barrido inmediato."""
        now = datetime.now(UTC)
        default_token = os.environ.get("WATCHGATE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

        with next(get_session()) as session:
            repo = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.id == repo_id,
                    MonitoredRepo.status == "active",
                    MonitoredRepo.auto_scan_prs == True,  # noqa: E712
                )
            ).first()

            if not repo:
                return None

            if not ignore_interval and repo.last_polled_at:
                elapsed = (now - repo.last_polled_at.replace(tzinfo=UTC)).total_seconds() / 60.0
                if elapsed < repo.scan_interval_minutes:
                    return None

            return cls._build_candidate_dict(repo, default_token, session)

    @classmethod
    def _poll_single_candidate(cls, candidate: dict[str, Any]) -> int:
        owner, repo_name = candidate["repo_path"].split("/", 1)
        client = GitHubClient(candidate["token"])
        now = datetime.now(UTC)
        total_enqueued = 0

        try:
            prs = client.list_all_open_pull_requests(owner, repo_name, max_prs=50)
            success = True
        except Exception:
            prs = None
            success = False

        # Actualizar estado HTTP y contador de errores en la BD
        with next(get_session()) as session:
            repo_db = session.get(MonitoredRepo, candidate["id"])
            if repo_db:
                repo_db.last_polled_at = now
                if success:
                    repo_db.consecutive_errors = 0
                else:
                    repo_db.consecutive_errors += 1
                    if repo_db.consecutive_errors >= 5:
                        repo_db.status = "error"
                session.commit()

        if not success or prs is None:
            return 0

        # Consultar PRs analizadas previamente con SQLModel y Dashboard DB
        analyzed_pr_ids: set[str] = set()
        with next(get_session()) as session:
            sql_prs = session.exec(
                select(PRScore.pr_id).where(PRScore.repo == candidate["repo_path"])
            ).all()
            analyzed_pr_ids.update(str(p) for p in sql_prs)

        try:
            from watchgate.dashboard.backend.db import db_session as dash_db_session

            with dash_db_session() as dash_conn:
                rows = dash_conn.execute(
                    "SELECT pr_id FROM pr_scores WHERE repo = ?", (candidate["repo_path"],)
                ).fetchall()
                for r in rows:
                    if r[0]:
                        analyzed_pr_ids.add(str(r[0]))
        except Exception:
            pass

        # Filtrar PRs abiertas nuevas (no analizadas aún)
        new_prs = [p for p in prs if str(p["number"]) not in analyzed_pr_ids]

        from watchgate.dashboard.backend.tasks import get_queue, run_audit_scan

        queue = get_queue()

        for pr in new_prs:
            pr_num = int(pr["number"])
            job_id = f"audit_pr:{candidate['repo_path']}:{pr_num}"

            existing_job = queue.fetch_job(job_id)
            if existing_job:
                if existing_job.is_failed:
                    existing_job.delete()
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

    @classmethod
    def poll_repo_by_id(cls, repo_id: str, ignore_interval: bool = True) -> int:
        """Efectúa el barrido de un repositorio concreto de forma inmediata."""
        candidate = cls.get_candidate_repo_by_id(repo_id, ignore_interval=ignore_interval)
        if not candidate:
            return 0
        return cls._poll_single_candidate(candidate)

    @classmethod
    def poll_all_candidates(cls, ignore_interval: bool = False) -> int:
        """Efectúa el barrido con llamadas HTTP sin bloqueo de transacciones DB."""
        candidates = cls.get_candidate_repos(ignore_interval=ignore_interval)
        total_enqueued = 0

        for candidate in candidates:
            total_enqueued += cls._poll_single_candidate(candidate)

        return total_enqueued
