"""Servicio de polling de repositorios externos (Clean Architecture & SRP)."""

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
    def get_candidate_repos(cls, ignore_interval: bool = False) -> list[dict[str, Any]]:
        """Obtiene la lista de repositorios candidatos cerrando la sesión de DB inmediatamente."""
        now = datetime.now(UTC)
        candidates: list[dict[str, Any]] = []
        default_token = os.environ.get("WATCHGATE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

        with next(get_session()) as session:
            repos = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.status == "active",
                    (MonitoredRepo.auto_scan_prs != False),  # noqa: E712
                )
            ).all()

            for repo in repos:
                if not ignore_interval and repo.last_polled_at:
                    interval = repo.scan_interval_minutes or 30
                    elapsed = (now - repo.last_polled_at.replace(tzinfo=UTC)).total_seconds() / 60.0
                    if elapsed < interval:
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
                    (MonitoredRepo.auto_scan_prs != False),  # noqa: E712
                )
            ).first()

            if not repo:
                return None

            if not ignore_interval and repo.last_polled_at:
                interval = repo.scan_interval_minutes or 30
                elapsed = (now - repo.last_polled_at.replace(tzinfo=UTC)).total_seconds() / 60.0
                if elapsed < interval:
                    return None

            return cls._build_candidate_dict(repo, default_token, session)

    @classmethod
    def _record_poll_outcome(cls, repo_id: str, now: datetime, success: bool) -> None:
        """Actualiza `last_polled_at`/`consecutive_errors`/`status` tras UN
        intento de barrido -- extraído a helper para poder llamarlo también
        desde el caso "repo_path mal formado" (ver `_poll_single_candidate`),
        que antes crasheaba ANTES de llegar aquí y nunca contaba como
        fallo."""
        with next(get_session()) as session:
            repo_db = session.get(MonitoredRepo, repo_id)
            if repo_db:
                repo_db.last_polled_at = now
                if repo_db.auto_scan_prs is None:
                    repo_db.auto_scan_prs = True
                if not repo_db.scan_interval_minutes:
                    repo_db.scan_interval_minutes = 30
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
            # GitHubClient no tiene nada que consultar. Antes esto hacía
            # `owner, repo_name = repo_path.split("/", 1)` a pelo, SIN
            # capturar: un ValueError sin coger aquí no solo mataba este
            # candidato, se propagaba hasta el `with redis_conn.lock(...)`
            # del scheduler y abortaba el barrido ENTERO -- ningún otro
            # repo (ni siquiera los válidos) se llegaba a comprobar
            # mientras existiera un solo repo_path mal formado en la BD
            # (hallazgo real, no hipotético: reproducido en vivo con dos
            # filas de prueba `prueba-1`/`prueba_watchgate` sin "/").
            # Se cuenta como un fallo más, por el MISMO camino de
            # consecutive_errors que un fallo de red -- tras 5 barridos
            # seguidos así, el repo pasa a status="error" y queda visible
            # en el dashboard en vez de fallar en silencio para siempre.
            logger.warning(
                "repo_path '%s' (id=%s) no tiene forma 'owner/repo' -- se omite y "
                "cuenta como fallo de barrido.",
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
            try:
                total_enqueued += cls._poll_single_candidate(candidate)
            except Exception as exc:  # noqa: BLE001 -- un fallo inesperado en UN
                # candidato (bug no previsto, no solo el repo_path mal formado ya
                # cubierto arriba) nunca debe impedir que se compruebe el resto --
                # hallazgo real: sin este aislamiento, dos filas de prueba con
                # repo_path sin "/" bastaban para que NINGÚN repo, ni siquiera los
                # válidos, se comprobara nunca en todo el proceso del scheduler.
                logger.warning(
                    "Fallo inesperado barriendo el repo '%s' (id=%s): %r",
                    candidate.get("repo_path"),
                    candidate.get("id"),
                    exc,
                )

        return total_enqueued
