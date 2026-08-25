from __future__ import annotations

import os
import re
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
from watchgate.db.models import MonitoredRepo, UserAPIKey, VCSConnection
from watchgate.db.repository import create_api_key

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


class ClaimInstallationIn(BaseModel):
    installation_id: str = Field(
        min_length=1,
        description="ID numérico de la instalación de la GitHub App (query `installation_id` "
        "de la Setup URL a la que GitHub redirige tras instalar la App)",
    )


class ClaimInstallationOut(BaseModel):
    vcs_connection_id: str
    installation_id: str
    app_configured: bool
    repos: list[MonitoredRepoResponse]


class GitServerRepoIn(BaseModel):
    repo_path: str = Field(
        description="Nombre visible del repo (ej: owner/repo), igual al que usará "
        "WATCHGATE_REPO_NAME en el hook pre-receive del servidor Git"
    )


class GitServerRepoOut(BaseModel):
    repo: MonitoredRepoResponse
    api_key: str = Field(
        description="Token wg_live_... para WATCHGATE_ENGINE_API_KEY en el hook "
        "pre-receive. Se muestra en claro solo esta vez -- solo se guarda su hash."
    )
    key_prefix: str
    engine_api_url: str = Field(
        description="URL pública del Engine API (WATCHGATE_ENGINE_API_PUBLIC_URL, "
        "o http://localhost:8080 si no está configurada) para rellenar "
        "WATCHGATE_ENGINE_API_URL en el hook."
    )
    hook_download_url: str = Field(
        description="GET directo al script del hook (watchgate/api/routers/hooks.py) "
        "-- instalar en un servidor Git real es un solo curl a esta URL."
    )


class GithubAppInfoOut(BaseModel):
    configured: bool = Field(
        description="True si el servidor tiene credenciales de la App "
        "(WATCHGATE_GITHUB_APP_ID + clave privada) para autenticar como App"
    )
    install_url: str | None = Field(
        description="URL pública para instalar la App (si WATCHGATE_GITHUB_APP_SLUG "
        "está configurado); None si la App aún no está registrada/anunciada"
    )


_JOB_ID_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_job_id_part(value: str) -> str:
    """RQ valida el `job_id` contra `[A-Za-z0-9_-]+` (`rq.job.JOB_ID_PATTERN`)
    -- un `repo_path` real como "owner/repo" (la barra) o
    "usuario/Curso.Prep.Henry" (el punto) lo revienta con un
    `ValueError: Job ID must only contain letters, numbers, underscores and
    dashes` (500 real, reproducido en `add_external_repo`/`scan_main_
    branch`, las dos únicas llamadas a `_enqueue_main_branch_scan`).
    Sustituye cualquier carácter no permitido por '_' -- no es una
    normalización perfecta (dos repo_path distintos podrían, en teoría,
    colisionar tras sanear), pero el peor caso es que un escaneo se trate
    como "ya en curso" y no se vuelva a encolar hasta que el existente
    termine, nunca un crash."""
    return _JOB_ID_UNSAFE_CHARS.sub("_", value)


def _enqueue_main_branch_scan(
    org_id: str, repo: MonitoredRepo, user_login: str | None = None
) -> bool:
    """Encola `run_main_branch_scan` (análisis del contenido COMPLETO de la
    rama por defecto, no solo de PRs) -- extraído para reusarse tanto al
    conectar un repo nuevo (`add_external_repo`, evento único de
    onboarding) como al pulsar "Escanear rama principal" a mano
    (`scan_main_branch`). Devuelve `False` sin encolar nada si ya hay un
    job para este repo en curso (ni failed ni terminado) -- mismo criterio
    que el resto de escaneos: no duplicar trabajo en vuelo.

    job_id incluye org_id (no solo repo_path): dos organizaciones
    distintas pueden auditar el MISMO repo_path (la unicidad de
    MonitoredRepo está bajo (org_id, repo_path), no bajo repo_path a
    secas) -- sin org_id aquí, la segunda colisionaría con el job de la
    primera. Se comprueba/borra un job previo con ese id antes de encolar
    -- MISMO patrón que RepoPollingService._poll_single_candidate: un
    job_id que ya existe en Redis (p. ej. de un intento anterior que
    falló) no se vuelve a encolar solo por llamar a queue.enqueue() con el
    mismo id -- se actualizan sus datos pero, si RQ ya lo sacó una vez de
    la lista de la cola, se queda "atascado" sin que ningún worker lo
    recoja nunca (comprobado en vivo).

    `user_login` (si se pasa) deja que `run_main_branch_scan` resuelva el
    token/URL de GitHub con prioridad al personal de ESE usuario (ver
    `resolve_github_credentials`, cascada de 5 niveles) -- en
    `add_external_repo` es quien conecta el repo; en `scan_main_branch` es
    quien pulsa el botón. Sin él, cae directamente al resto de la cascada
    (VCSConnection del repo / fallback de organización / variables de
    entorno / anónimo).
    """
    queue = get_queue()
    job_id = f"main_branch_scan-{_safe_job_id_part(org_id)}-{_safe_job_id_part(repo.repo_path)}"
    existing_job = queue.fetch_job(job_id)
    if existing_job is not None and not existing_job.is_failed:
        return False
    if existing_job is not None:
        existing_job.delete()
    queue.enqueue(
        run_main_branch_scan,
        repo.repo_path,
        org_id,
        repo.vcs_connection_id,
        user_login=user_login,
        job_id=job_id,
    )
    return True


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
    # repo ya conectado requiere pulsar un botón "Escanear..." en el
    # Dashboard (ver `scan_main_branch`/`scan_audited_repo` más abajo).
    if new_repo.monitor_type == "audited":
        _enqueue_main_branch_scan(org_id, new_repo, user_login=user_login)

    # Escaneo inmediato (único, al conectar) de todas las PRs abiertas ya
    # existentes -- igual que el escaneo de línea base de arriba, evento de
    # onboarding, no repolling periódico.
    from watchgate.service.repo_polling import RepoPollingService

    RepoPollingService.poll_repo_by_id(new_repo.id)

    return new_repo


@router.post("/git-server", response_model=GitServerRepoOut, status_code=status.HTTP_201_CREATED)
def connect_git_server_repo(
    data: GitServerRepoIn,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Da de alta un repo de servidor Git propio (`monitor_type="git_server"`,
    hook `pre-receive` -- ver docs/manual_git_hooks.md §6) ANTES de su
    primer push, en un solo paso pensado para copiar/pegar en el hook: crea
    el `MonitoredRepo` Y una API key ya atada a él, y devuelve el token en
    claro.

    A diferencia de `add_external_repo`, aquí NO se llama a
    `RepoPollingService.poll_repo_by_id` -- ese polling asume un repo de
    GitHub (PRs vía API), que no existe para un servidor Git propio; el
    único análisis real llega del propio hook en cada push, nunca de aquí.
    """
    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None, "El usuario debe tener una organización"

    repo_path_cleaned = data.repo_path.strip().strip("/")

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
        repo_path=repo_path_cleaned,
        monitor_type="git_server",
        status="active",
        created_at=datetime.now(UTC),
    )
    session.add(new_repo)
    session.commit()
    session.refresh(new_repo)

    api_key, raw_token = create_api_key(
        session=session,
        user_id=db_user.id,
        org_id=org_id,
        monitored_repo_id=new_repo.id,
        name=f"Hook servidor Git: {repo_path_cleaned}",
    )

    engine_api_url = (
        os.environ.get("WATCHGATE_ENGINE_API_PUBLIC_URL") or "http://localhost:8080"
    ).rstrip("/")

    return {
        "repo": new_repo,
        "api_key": raw_token,
        "key_prefix": api_key.key_prefix,
        "engine_api_url": engine_api_url,
        "hook_download_url": f"{engine_api_url}/api/v1/hooks/pre-receive",
    }


@router.get("/github-app", response_model=GithubAppInfoOut)
def github_app_info(_current_user: CurrentUser) -> GithubAppInfoOut:
    """Estado de la GitHub App para que el dashboard pinte (o no) el botón
    "Instalar GitHub App" en la página de conexión de repositorios.

    `install_url` sale del slug público de la App
    (`WATCHGATE_GITHUB_APP_SLUG`, el nombre en la URL github.com/apps/<slug>)
    -- es un dato público, no una credencial. `configured` indica si el
    servidor además puede autenticar como App (listar repos de una
    instalación, tokens efímeros); pueden darse por separado: un despliegue
    puede anunciar la App sin tener la clave privada aún, y viceversa.
    """
    from watchgate.adapters.github_app import github_app_configured

    slug = (os.environ.get("WATCHGATE_GITHUB_APP_SLUG") or "").strip()
    return GithubAppInfoOut(
        configured=github_app_configured(),
        install_url=f"https://github.com/apps/{slug}/installations/new" if slug else None,
    )


@router.post(
    "/installations/claim",
    response_model=ClaimInstallationOut,
    status_code=status.HTTP_201_CREATED,
)
def claim_installation(
    data: ClaimInstallationIn,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Reclama una instalación de la GitHub App para la organización del
    usuario autenticado -- el eslabón que faltaba del modo "managed".

    Contexto: el webhook de PRs (`routers/webhooks.py` -> `run_managed_scan`)
    resuelve la organización buscando una `VCSConnection` por
    `installation_id`... pero hasta este endpoint NADA creaba esa fila:
    instalar la App no tenía ningún efecto (el worker devolvía "no
    registrado" en silencio). El flujo completo ahora es:

    1. El usuario instala la App de WatchGate en su repo/organización de
       GitHub.
    2. GitHub redirige su navegador a la Setup URL configurada en la App
       (la página de repos externos del dashboard) con
       `?installation_id=<id>&setup_action=install`.
    3. El frontend, con la sesión del dashboard ya iniciada, llama aquí.
    4. Se crea la `VCSConnection` (org del usuario <-> installation_id) y,
       si la App está configurada en el servidor (WATCHGATE_GITHUB_APP_ID
       + clave privada), se dan de alta como "managed" los repos a los que
       la instalación da acceso. A partir de ese momento los webhooks de
       PR de esos repos encuentran la conexión y los escaneos corren.

    Idempotente para la misma organización (reclamar dos veces devuelve lo
    mismo); 409 si otra organización ya la reclamó.
    """
    from watchgate.adapters.github_app import (
        github_app_configured,
        list_installation_repositories,
    )

    installation_id = data.installation_id.strip()
    if not installation_id.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="installation_id debe ser el ID numérico de la instalación de GitHub.",
        )

    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None

    existing_vcs = session.exec(
        select(VCSConnection).where(VCSConnection.installation_id == installation_id)
    ).first()
    if existing_vcs is not None and existing_vcs.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta instalación ya está reclamada por otra organización.",
        )
    if existing_vcs is not None:
        vcs = existing_vcs
    else:
        vcs = VCSConnection(
            id=str(uuid4()),
            org_id=org_id,
            provider="github",
            installation_id=installation_id,
        )
        session.add(vcs)
        session.commit()
        session.refresh(vcs)

    app_configured = github_app_configured()
    created_or_existing: list[MonitoredRepo] = []
    if app_configured:
        for repo_path in list_installation_repositories(installation_id):
            repo = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path
                )
            ).first()
            if repo is None:
                repo = MonitoredRepo(
                    id=str(uuid4()),
                    org_id=org_id,
                    vcs_connection_id=vcs.id,
                    repo_path=repo_path,
                    monitor_type="managed",
                    status="active",
                    created_at=datetime.now(UTC),
                )
                session.add(repo)
                session.commit()
                session.refresh(repo)
            elif repo.vcs_connection_id is None:
                # Ya estaba (p. ej. en modo audited): se vincula a la
                # instalación sin duplicar la fila ni cambiar su modo.
                repo.vcs_connection_id = vcs.id
                session.add(repo)
                session.commit()
                session.refresh(repo)
            created_or_existing.append(repo)

    return ClaimInstallationOut(
        vcs_connection_id=vcs.id,
        installation_id=installation_id,
        app_configured=app_configured,
        repos=[
            MonitoredRepoResponse.model_validate(r, from_attributes=True)
            for r in created_or_existing
        ],
    )


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
            run_audit_scan,
            repo.repo_path,
            scan_data.pr_number,
            org_id,
            repo.vcs_connection_id,
            user_login=user_login,
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


@router.post("/{repo_id}/scan-main", status_code=status.HTTP_202_ACCEPTED)
def scan_main_branch(
    repo_id: str,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Encola un análisis del contenido COMPLETO de la rama por defecto
    (no de una PR concreta) -- botón "Escanear rama principal" del
    Dashboard. Mismo `run_main_branch_scan` que ya se dispara una única
    vez al conectar un repo "audited" (`add_external_repo`), pero aquí
    bajo demanda y para cualquier repo (también "managed": las PRs le
    llegan por webhook, pero el contenido YA existente de la rama
    principal antes de activar el webhook no queda cubierto por eso).
    Queda reflejado en el historial del repo como cualquier otro análisis
    (`pr_id` = "main")."""
    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None

    repo = session.exec(
        select(MonitoredRepo).where(MonitoredRepo.id == repo_id, MonitoredRepo.org_id == org_id)
    ).first()

    if not repo:
        raise HTTPException(status_code=404, detail="Repositorio no encontrado")

    enqueued = _enqueue_main_branch_scan(org_id, repo, user_login=user_login)
    return {
        "message": "Escaneo de la rama principal encolado"
        if enqueued
        else "Ya hay un escaneo de la rama principal en curso para este repositorio",
        "repo_path": repo.repo_path,
        "enqueued": enqueued,
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


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_external_repo(
    repo_id: str,
    current_user: CurrentUser,
    session: DBSession,
    request: Request,
) -> None:
    """Deja de monitorizar/auditar un repositorio externo.

    Decisión explícita del equipo (2026-08-17): borra solo el registro de
    `MonitoredRepo` (deja de escanearse y desaparece de la lista) -- NUNCA
    el histórico de análisis ya hechos (`pr_scores` en la base del
    Dashboard, tabla separada sin FK hacia `monitored_repos`, ver
    `db.py::DashboardPRScore`). Un repo que se deja de auditar no debe
    perder su rastro de auditoría pasado.

    Bloquea el borrado (409) si hay alguna API key de agente atada a este
    repo (`UserAPIKey.monitored_repo_id`, FK real hacia esta tabla) -- en
    vez de dejar que la FK reviente con un IntegrityError opaco, o (la
    alternativa fácil pero peligrosa) poner esa columna a NULL en silencio,
    lo que degradaría esa key a "legado" validada solo por org_id sin que
    quien la creó se entere de que perdió su alcance acotado a un repo."""
    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None

    repo = session.exec(
        select(MonitoredRepo).where(MonitoredRepo.id == repo_id, MonitoredRepo.org_id == org_id)
    ).first()

    if not repo:
        raise HTTPException(status_code=404, detail="Repositorio no encontrado")

    require_role(current_user, repo.repo_path, min_role="mantenedor", request=request)

    bound_keys = session.exec(
        select(UserAPIKey).where(UserAPIKey.monitored_repo_id == repo_id)
    ).all()
    if bound_keys:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede eliminar: hay {len(bound_keys)} API key(s) de agente atadas a "
                "este repositorio. Revócalas o reasígnalas a otro repo primero."
            ),
        )

    session.delete(repo)
    session.commit()
