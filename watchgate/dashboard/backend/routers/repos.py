from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from watchgate.dashboard.backend.auth import CurrentUser, require_role
from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
from watchgate.dashboard.backend.schemas import normalize_login
from watchgate.dashboard.backend.tasks import get_queue, run_audit_scan, run_main_branch_scan
from watchgate.db.connection import get_db_session
from watchgate.db.models import MonitoredRepo, VCSConnection

DBSession = Annotated[Session, Depends(get_db_session)]

router = APIRouter(prefix="/repos/external", tags=["repos"])


class MonitoredRepoCreate(BaseModel):
    repo_path: str = Field(description="Ruta del repositorio (ej: owner/repo)")
    monitor_type: str = Field(
        default="managed", description="'managed' (webhook) o 'audited' (sin permisos)"
    )
    vcs_connection_id: str | None = Field(
        default=None, description="ID de la conexión VCS si aplica"
    )


class MonitoredRepoResponse(BaseModel):
    id: str
    vcs_connection_id: str | None
    repo_path: str
    monitor_type: str
    status: str
    last_scanned_at: datetime | None
    last_polled_at: datetime | None
    consecutive_errors: int
    created_at: datetime


class MonitoredRepoUpdate(BaseModel):
    status: str | None = Field(default=None, description="'active', 'paused' o 'error'")


class ScanRequest(BaseModel):
    pr_number: int | None = Field(
        default=None, description="Número de PR a auditar (0 o None para todas las PRs abiertas)"
    )


@router.post("", response_model=MonitoredRepoResponse, status_code=status.HTTP_201_CREATED)
def add_external_repo(
    data: MonitoredRepoCreate,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Añade un repositorio externo para monitorización (webhook) o auditoría (sin permisos)."""

    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)

    # db_user.org_id está garantizado por _get_or_create_db_user
    org_id = db_user.org_id
    assert org_id is not None, "El usuario debe tener una organización"

    # Si se pasa un vcs_connection_id, verificar que pertenezca a la org
    if data.vcs_connection_id:
        vcs = session.exec(
            select(VCSConnection).where(
                VCSConnection.id == data.vcs_connection_id, VCSConnection.org_id == org_id
            )
        ).first()
        if not vcs:
            raise HTTPException(status_code=404, detail="Conexión VCS no encontrada")

    # Extraer "owner/repo" por si el usuario metió un enlace completo
    repo_path_cleaned = data.repo_path
    if repo_path_cleaned.startswith("http"):
        # Intenta extraer la ruta final (e.g. owner/repo)
        import re

        match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git|/)?$", repo_path_cleaned)
        if match:
            repo_path_cleaned = match.group(1)

    # Verificar si ya existe en la org
    existing = session.exec(
        select(MonitoredRepo).where(
            MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path_cleaned
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=409, detail="El repositorio ya está monitorizado en esta organización"
        )

    new_repo = MonitoredRepo(
        id=str(uuid4()),
        org_id=org_id,
        vcs_connection_id=data.vcs_connection_id,
        repo_path=repo_path_cleaned,
        monitor_type=data.monitor_type,
        status="active",
        created_at=datetime.now(UTC),
    )
    session.add(new_repo)
    session.commit()
    session.refresh(new_repo)

    # Escaneo de línea base: al dar de alta un repo en auditoría externa
    # ("audited", sin permisos de escritura -- distinto de "managed", que
    # llega vía GitHub App/webhook), se encola un análisis del contenido
    # COMPLETO de su rama por defecto, no solo de sus PRs futuras -- ver
    # tasks.py:run_main_branch_scan. Sin esto, un repo con historial ya
    # existente se queda sin ninguna foto de riesgo hasta que alguien pulse
    # "Escanear" o abra la primera PR nueva. Evento ÚNICO al conectar el
    # repo, no periódico -- el repolling automático se eliminó (ver
    # watchgate/service/repo_polling.py); todo escaneo POSTERIOR de un
    # repo ya conectado requiere pulsar "Escanear" en el Dashboard.
    #
    # job_id incluye org_id (no solo repo_path): dos organizaciones
    # distintas pueden auditar el MISMO repo_path (la unicidad de arriba
    # está bajo (org_id, repo_path), no bajo repo_path a secas) -- sin
    # org_id aquí, la segunda colisionaría con el job de la primera.
    #
    # Se comprueba/borra un job previo con ese id antes de encolar --
    # MISMO patrón que RepoPollingService._poll_single_candidate: un
    # job_id que ya existe en Redis (p. ej. de un intento anterior que
    # falló) no se vuelve a encolar solo por llamar a queue.enqueue() con
    # el mismo id -- se actualizan sus datos pero, si RQ ya lo sacó una vez
    # de la lista de la cola, se queda "atascado" sin que ningún worker lo
    # recoja nunca (comprobado en vivo).
    if new_repo.monitor_type == "audited":
        queue = get_queue()
        job_id = f"main_branch_scan:{org_id}:{new_repo.repo_path}"
        existing_job = queue.fetch_job(job_id)
        if existing_job is None or existing_job.is_failed:
            if existing_job is not None:
                existing_job.delete()
            queue.enqueue(
                run_main_branch_scan,
                new_repo.repo_path,
                org_id,
                new_repo.vcs_connection_id,
                job_id=job_id,
            )

    # Escaneo inmediato (único, al conectar) de todas las PRs abiertas ya
    # existentes -- igual que el escaneo de línea base de arriba, evento de
    # onboarding, no repolling periódico.
    from watchgate.service.repo_polling import RepoPollingService

    RepoPollingService.poll_repo_by_id(new_repo.id)

    return new_repo


@router.get("", response_model=list[MonitoredRepoResponse])
def list_external_repos(
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Lista los repositorios externos de la organización actual."""
    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None

    repos = session.exec(select(MonitoredRepo).where(MonitoredRepo.org_id == org_id)).all()

    return repos


@router.post("/{repo_id}/scan", status_code=status.HTTP_202_ACCEPTED)
def scan_audited_repo(
    repo_id: str,
    scan_data: ScanRequest,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Encola el escaneo de una PR concreta o de todas las PRs abiertas de un repositorio."""
    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None

    repo = session.exec(
        select(MonitoredRepo).where(MonitoredRepo.id == repo_id, MonitoredRepo.org_id == org_id)
    ).first()

    if not repo:
        raise HTTPException(status_code=404, detail="Repositorio no encontrado")

    if scan_data.pr_number and scan_data.pr_number > 0:
        queue = get_queue()
        queue.enqueue(
            run_audit_scan, repo.repo_path, scan_data.pr_number, org_id, repo.vcs_connection_id
        )
        return {
            "message": "Escaneo de PR encolado",
            "repo_path": repo.repo_path,
            "pr_number": scan_data.pr_number,
        }

    from watchgate.service.repo_polling import RepoPollingService

    enqueued = RepoPollingService.poll_repo_by_id(repo.id)
    return {
        "message": f"Escaneo de todas las PRs abiertas encolado ({enqueued} PRs)",
        "repo_path": repo.repo_path,
        "prs_enqueued": enqueued,
    }


@router.patch("/{repo_id}", response_model=MonitoredRepoResponse)
def update_external_repo(
    repo_id: str,
    data: MonitoredRepoUpdate,
    current_user: CurrentUser,
    session: DBSession,
    request: Request,
) -> Any:
    """Actualiza el estado (activo/pausado) de un repositorio externo."""
    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None

    repo = session.exec(
        select(MonitoredRepo).where(MonitoredRepo.id == repo_id, MonitoredRepo.org_id == org_id)
    ).first()

    if not repo:
        raise HTTPException(status_code=404, detail="Repositorio no encontrado")

    # Verificación de permisos RBAC
    require_role(current_user, repo.repo_path, min_role="mantenedor", request=request)

    if data.status is not None:
        if data.status not in ("active", "paused", "error"):
            raise HTTPException(status_code=400, detail="Estado inválido")
        repo.status = data.status

    session.commit()
    session.refresh(repo)
    return repo
