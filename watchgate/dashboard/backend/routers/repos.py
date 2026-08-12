from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import normalize_login
from watchgate.dashboard.backend.tasks import get_queue, run_audit_scan
from watchgate.db.connection import get_db_session
from watchgate.db.models import MonitoredRepo, VCSConnection
from watchgate.db.models import User as DBUser

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
    created_at: datetime


class ScanRequest(BaseModel):
    pr_number: int = Field(description="Número de la Pull Request a auditar")


@router.post("", response_model=MonitoredRepoResponse, status_code=status.HTTP_201_CREATED)
def add_external_repo(
    data: MonitoredRepoCreate,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Añade un repositorio externo para monitorización (webhook) o auditoría (sin permisos)."""

    # Check if the user exists in DB and has an org.
    # CurrentUser gives us dashboard's schema User, we need DBUser to get org_id
    user_login = normalize_login(current_user.login)
    stmt = select(DBUser).where(DBUser.email == user_login)
    db_user = session.exec(stmt).first()

    if not db_user or not db_user.org_id:
        raise HTTPException(
            status_code=400, detail="El usuario no pertenece a ninguna organización"
        )

    # Si se pasa un vcs_connection_id, verificar que pertenezca a la org
    if data.vcs_connection_id:
        vcs = session.exec(
            select(VCSConnection).where(
                VCSConnection.id == data.vcs_connection_id, VCSConnection.org_id == db_user.org_id
            )
        ).first()
        if not vcs:
            raise HTTPException(status_code=404, detail="Conexión VCS no encontrada")

    # Verificar si ya existe en la org
    existing = session.exec(
        select(MonitoredRepo).where(
            MonitoredRepo.org_id == db_user.org_id, MonitoredRepo.repo_path == data.repo_path
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=409, detail="El repositorio ya está monitorizado en esta organización"
        )

    new_repo = MonitoredRepo(
        id=str(uuid4()),
        org_id=db_user.org_id,
        vcs_connection_id=data.vcs_connection_id,
        repo_path=data.repo_path,
        monitor_type=data.monitor_type,
        status="active",
        created_at=datetime.now(UTC),
    )
    session.add(new_repo)
    session.commit()
    session.refresh(new_repo)

    return new_repo


@router.get("", response_model=list[MonitoredRepoResponse])
def list_external_repos(
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Lista los repositorios externos de la organización actual."""
    user_login = normalize_login(current_user.login)
    stmt = select(DBUser).where(DBUser.email == user_login)
    db_user = session.exec(stmt).first()

    if not db_user or not db_user.org_id:
        return []

    repos = session.exec(select(MonitoredRepo).where(MonitoredRepo.org_id == db_user.org_id)).all()

    return repos


@router.post("/{repo_id}/scan", status_code=status.HTTP_202_ACCEPTED)
def scan_audited_repo(
    repo_id: str,
    scan_data: ScanRequest,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Encola el escaneo de una PR concreta de un repositorio auditado."""
    user_login = normalize_login(current_user.login)
    stmt = select(DBUser).where(DBUser.email == user_login)
    db_user = session.exec(stmt).first()

    if not db_user or not db_user.org_id:
        raise HTTPException(status_code=400, detail="Organización no encontrada")

    repo = session.exec(
        select(MonitoredRepo).where(
            MonitoredRepo.id == repo_id, MonitoredRepo.org_id == db_user.org_id
        )
    ).first()

    if not repo:
        raise HTTPException(status_code=404, detail="Repositorio no encontrado")

    if repo.monitor_type != "audited":
        raise HTTPException(
            status_code=400, detail="Sólo se puede auditar manualmente repositorios tipo 'audited'"
        )

    queue = get_queue()
    queue.enqueue(
        run_audit_scan, repo.repo_path, scan_data.pr_number, db_user.org_id, repo.vcs_connection_id
    )

    return {
        "message": "Escaneo de PR encolado",
        "repo_path": repo.repo_path,
        "pr_number": scan_data.pr_number,
    }
