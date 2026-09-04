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
import re
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select

from watchgate.adapters.github_client import GitHubClient
from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo, PRScore, VCSConnection

logger = logging.getLogger("watchgate.repo_polling")

_JOB_ID_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def safe_job_id_part(value: str) -> str:
    """RQ valida el `job_id` contra `[A-Za-z0-9_-]+` (`rq.job.JOB_ID_PATTERN`,
    `fullmatch`) -- un `repo_path` real como "owner/repo" (la barra) o
    "usuario/Curso.Prep.Henry" (el punto) lo revienta con un
    `ValueError: Job ID must only contain letters, numbers, underscores and
    dashes`. Sustituye cualquier carácter no permitido por '_' -- no es una
    normalización perfecta (dos repo_path distintos podrían, en teoría,
    colisionar tras sanear), pero el peor caso es que un escaneo se trate
    como "ya en curso" y no se vuelva a encolar hasta que el existente
    termine, nunca un crash.

    Único fuente -- `routers/repos.py::_enqueue_main_branch_scan` reexporta
    este mismo símbolo en vez de duplicarlo (ver también
    `_poll_single_candidate` más abajo, que hasta ahora construía su propio
    `job_id` con ':' como separador SIN pasar por aquí -- mismo bug de
    ValueError, reproducido en vivo contra PRs reales de GitHub, solo que
    en el escaneo de PRs en vez de en el de rama principal)."""
    return _JOB_ID_UNSAFE_CHARS.sub("_", value)


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
        fallo, y desde `record_scan_outcome` (ver más abajo)."""
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
    def record_scan_outcome(cls, repo_id: str, success: bool) -> None:
        """Punto de entrada público para que `dashboard/backend/tasks.py`
        refleje en `MonitoredRepo` el resultado de un escaneo QUE YA SE
        EJECUTÓ (`run_audit_scan`/`run_managed_scan`/`run_main_branch_scan`),
        no solo el de listar las PRs abiertas (que es lo único que cubría
        `_record_poll_outcome` hasta ahora, llamado únicamente desde
        `_poll_single_candidate`). Antes de esto, una excepción del propio
        análisis (token inválido, PR inexistente, fallo de red al llamar a
        la API de GitHub...) no dejaba ningún rastro en `consecutive_errors`
        ni `status` -- el repo se quedaba "active" aunque cada escaneo
        real fallase en silencio. Mismo criterio de "5 fallos seguidos ->
        status=error" que ya usa el resto del servicio, deliberadamente
        unificado en un solo contador por repo en vez de uno por tipo de
        fallo (listar vs. analizar): para el usuario ambos significan
        "este repo lleva un tiempo sin poder hablar con GitHub"."""
        cls._record_poll_outcome(repo_id, datetime.now(UTC), success)

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

        open_pr_ids = {str(p["number"]) for p in prs}

        # PRs ya analizadas (trackeadas) que ya NO aparecen en la lista de
        # abiertas de GitHub -- se cerraron o se mergearon desde el último
        # barrido. Se marcan (pr_state="closed"), nunca se borran: el
        # análisis y su histórico se conservan, solo dejan de contar como
        # "pendientes" en el dashboard (ver db.py::mark_prs_closed). Best
        # effort igual que el resto de escritura en la BD del Dashboard de
        # este método -- un fallo aquí no debe tumbar el resto del barrido
        # (encolar las PRs nuevas de abajo sigue siendo lo prioritario).
        closed_pr_ids = analyzed_pr_ids - open_pr_ids
        if closed_pr_ids:
            try:
                from watchgate.dashboard.backend.db import db_session as dash_db_session
                from watchgate.dashboard.backend.db import mark_prs_closed

                with dash_db_session() as dash_session:
                    mark_prs_closed(dash_session, candidate["repo_path"], closed_pr_ids)
            except Exception:
                logger.warning(
                    "No se pudieron marcar como cerradas las PRs %s de '%s' -- se reintentará "
                    "en el próximo barrido.",
                    closed_pr_ids,
                    candidate["repo_path"],
                )

        # Filtrar PRs abiertas nuevas (no analizadas aún)
        new_prs = [p for p in prs if str(p["number"]) not in analyzed_pr_ids]

        from watchgate.dashboard.backend.tasks import (
            ANALYSIS_JOB_TIMEOUT_SECONDS,
            get_queue,
            run_audit_scan,
        )

        queue = get_queue()

        for pr in new_prs:
            pr_num = int(pr["number"])
            # Guion, no ':' -- ver `safe_job_id_part`. Antes de este fix,
            # CUALQUIER repo "audited" con al menos una PR abierta nueva
            # hacía saltar `ValueError: Job ID must only contain letters,
            # numbers, underscores and dashes` aquí mismo (reproducido en
            # vivo contra PRs reales de GitHub) -- ni el escaneo automático
            # al conectar el repo ni el botón "Escanear" llegaban a encolar
            # NINGUNA PR, aunque el repo se hubiera creado correctamente.
            job_id = f"audit_pr-{safe_job_id_part(candidate['repo_path'])}-{pr_num}"

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
                job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
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
