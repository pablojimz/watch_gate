"""Escaneo bajo demanda de repositorios externos (Clean Architecture & SRP).

Antes había también un barrido PERIÓDICO automático (cada
`scan_interval_minutes`, disparado por un proceso `scheduler` aparte) --
eliminado a petición explícita: todo escaneo de PRs de un repo ya
conectado ahora requiere que alguien pulse "Escanear" en el Dashboard
(`POST /api/repos/external/{id}/scan`, ver `routers/repos.py`) o, en el
caso de `run_main_branch_scan`, se dispara una única vez al dar de alta el
repo (evento puntual de onboarding, no periódico -- eso sigue igual). Este
módulo ya solo resuelve UN repo concreto por su id, nunca "todos los
candidatos vencidos".
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select

from watchgate.adapters.github_client import GitHubClient
from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo, PRScore, VCSConnection

logger = logging.getLogger("watchgate.repo_polling")


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
    def get_candidate_repo_by_id(cls, repo_id: str) -> dict[str, Any] | None:
        """Resuelve un repo concreto para un escaneo manual inmediato --
        `None` si no existe o está `paused`/`error` (un repo pausado no se
        escanea ni a mano; hay que reactivarlo primero vía
        `PATCH /api/repos/external/{id}` con `status: "active"`)."""
        default_token = os.environ.get("WATCHGATE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

        with next(get_session()) as session:
            repo = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.id == repo_id,
                    MonitoredRepo.status == "active",
                )
            ).first()

            if not repo:
                return None

            return cls._build_candidate_dict(repo, default_token, session)

    @classmethod
    def _record_poll_outcome(cls, repo_id: str, now: datetime, success: bool) -> None:
        """Actualiza `last_polled_at`/`consecutive_errors`/`status` tras UN
        intento de escaneo -- extraído a helper para poder llamarlo también
        desde el caso "repo_path mal formado" (ver `_poll_single_candidate`),
        que antes crasheaba ANTES de llegar aquí y nunca contaba como
        fallo."""
        with next(get_session()) as session:
            repo_db = session.get(MonitoredRepo, repo_id)
            if repo_db:
                repo_db.last_polled_at = now
                if success:
                    repo_db.consecutive_errors = 0
                else:
                    repo_db.consecutive_errors += 1
                    if repo_db.consecutive_errors >= 5:
                        repo_db.status = "error"
                session.commit()

    @classmethod
    def _poll_single_candidate(cls, candidate: dict[str, Any]) -> int:
        now = datetime.now(UTC)
        total_enqueued = 0

        repo_path = candidate["repo_path"]
        owner_repo = repo_path.split("/", 1)
        if len(owner_repo) != 2 or not owner_repo[0] or not owner_repo[1]:
            # repo_path no tiene forma "owner/repo" (p. ej. quedó de una
            # prueba con un repo git local, sin dueño de GitHub) --
            # GitHubClient no tiene nada que consultar. Se cuenta como un
            # fallo más, por el MISMO camino de consecutive_errors que un
            # fallo de red -- tras 5 escaneos seguidos así, el repo pasa a
            # status="error" y queda visible en el dashboard en vez de
            # fallar en silencio para siempre.
            logger.warning(
                "repo_path '%s' (id=%s) no tiene forma 'owner/repo' -- se omite y "
                "cuenta como fallo de escaneo.",
                repo_path,
                candidate["id"],
            )
            cls._record_poll_outcome(candidate["id"], now, success=False)
            return 0
        owner, repo_name = owner_repo

        client = GitHubClient(candidate["token"])

        try:
            prs = client.list_all_open_pull_requests(owner, repo_name, max_prs=50)
            success = True
        except Exception:
            prs = None
            success = False

        cls._record_poll_outcome(candidate["id"], now, success)

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
            from watchgate.dashboard.backend.db import list_pr_numbers_for_repo

            with dash_db_session() as dash_session:
                analyzed_pr_ids.update(
                    list_pr_numbers_for_repo(dash_session, candidate["repo_path"])
                )
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
    def poll_repo_by_id(cls, repo_id: str) -> int:
        """Escanea un repositorio concreto ahora mismo -- único punto de
        entrada de este servicio: `POST /api/repos/external/{id}/scan`
        (botón "Escanear" del Dashboard) y el escaneo puntual al conectar
        un repo nuevo (`routers/repos.py::add_external_repo`)."""
        candidate = cls.get_candidate_repo_by_id(repo_id)
        if not candidate:
            return 0
        return cls._poll_single_candidate(candidate)
