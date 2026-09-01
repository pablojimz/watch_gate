"""scores.py — endpoints de histórico de puntuaciones y repos visibles."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import select

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser, require_ingest_token, require_role
from watchgate.dashboard.backend.live_events import stream_repo_events
from watchgate.dashboard.backend.org_scope import (
    is_site_superadmin,
    resolve_caller_org_id,
    resolve_org_repo_paths,
)
from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user
from watchgate.dashboard.backend.routers.repos import (
    DBSession,
    _enqueue_repo_knowledge_graph,
    delete_monitored_repo_cascade,
)
from watchgate.dashboard.backend.schemas import (
    CiConfigOut,
    IngestScoreIn,
    RepoSettings,
    ScoreOut,
    normalize_login,
)
from watchgate.db.models import (
    BlockedAuthor,
    MonitoredRepo,
    PRScore,
    RepoArchitectureSummary,
    RepoGraphNode,
    UserAPIKey,
)

router = APIRouter(tags=["scores"])


class RepoGraphNodeOut(BaseModel):
    file_path: str
    language: str | None
    category: str
    summary: str
    symbols: list[str]
    imports: list[str]
    loc: int


class RepoKnowledgeGraphOut(BaseModel):
    status: str  # "pending" | "building" | "ready" | "error"
    error_message: str | None
    overview: str
    project_type: str | None
    languages: str | None
    module_breakdown: list[dict[str, Any]]
    node_count: int
    edge_count: int
    built_at: datetime | None
    nodes: list[RepoGraphNodeOut]


@router.get("/repos")
def list_visible_repos(user: CurrentUser) -> list[str]:
    # Se quitó el rol "admin_organizacion" del RBAC -- ya no hay ningún
    # rol capaz de ver TODOS los repos de una organización sin tener rol
    # explícito en cada uno; cada quien ve solo los repos donde tiene una
    # fila real en repo_roles. Único que sigue viendo todo: el superadmin
    # de sitio, a propósito (`unscoped=True`, nunca por un `org_id` vacío
    # -- ver el bugfix en list_repos_for_user), mismo nivel que ya tiene
    # sobre llm_settings.py/ui_settings.py, coherente con administrar la
    # instancia entera.
    caller_is_site_superadmin = is_site_superadmin(user.login)

    from watchgate.db.connection import get_session

    with next(get_session()) as engine_session:
        org_id = resolve_caller_org_id(engine_session, user.login)
        org_repo_paths = resolve_org_repo_paths(engine_session, org_id)
    with database.db_session() as conn:
        return database.list_repos_for_user(
            conn,
            user.login,
            is_admin=caller_is_site_superadmin,
            org_id=org_id,
            org_repo_paths=org_repo_paths,
            unscoped=caller_is_site_superadmin,
        )


@router.get("/repos/{repo:path}/scores", response_model=list[ScoreOut])
def list_scores(repo: str, request: Request, user: CurrentUser) -> list[ScoreOut]:
    require_role(user, repo, min_role="revisor", request=request)
    with database.db_session() as conn:
        return database.list_scores(conn, repo)


@router.get("/repos/{repo:path}/events")
def stream_scores(repo: str, request: Request, user: CurrentUser) -> StreamingResponse:
    """SSE: un `data: refresh` cada vez que `repo` tiene un score nuevo --
    ver live_events.py. Mismo control de acceso que /scores (mismo dato,
    solo cambia el transporte)."""
    require_role(user, repo, min_role="revisor", request=request)
    return StreamingResponse(
        stream_repo_events(repo),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx (ver nginx.conf.template): no bufferizar esta
            # respuesta -- sin esto, los eventos se quedarían atascados en
            # el buffer de proxy hasta acumular varios KB o cerrar la
            # conexión, en vez de llegar al navegador al instante.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/settings/defaults", response_model=RepoSettings)
def get_default_settings(_user: CurrentUser) -> RepoSettings:
    with database.db_session() as conn:
        return database.get_org_settings(conn)


@router.put("/settings/defaults", response_model=RepoSettings)
def put_default_settings(body: RepoSettings, user: CurrentUser) -> RepoSettings:
    # Auditoría: `org_settings` es una fila SINGLETON compartida por TODA
    # la instancia (get_org_settings/set_org_settings, sin `org_id` en
    # ningún sitio) -- no es un dato por-organización, así que ya no basta
    # con `admin_organizacion` (ahora acotado por org) -- exige superadmin
    # de sitio (mismo criterio que llm_settings.py/ui_settings.py).
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )
    with database.db_session() as conn:
        return database.set_org_settings(conn, body)


@router.get("/repos/{repo:path}/settings", response_model=RepoSettings)
def get_repo_settings(repo: str, request: Request, user: CurrentUser) -> RepoSettings:
    require_role(user, repo, min_role="revisor", request=request)
    with database.db_session() as conn:
        return database.get_settings(conn, repo)


@router.put("/repos/{repo:path}/settings", response_model=RepoSettings)
def put_repo_settings(
    repo: str, body: RepoSettings, request: Request, user: CurrentUser
) -> RepoSettings:
    # Se quitó el rol "admin_organizacion" del RBAC -- el dueño del repo
    # (mantenedor, ya con autoridad sobre todo lo demás de este repo
    # concreto) es ahora quien decide sus propios pesos/umbrales/política.
    require_role(user, repo, min_role="mantenedor", request=request)
    with database.db_session() as conn:
        return database.set_settings(conn, repo, body)


@router.delete("/repos/{repo:path}/settings", response_model=RepoSettings)
def reset_repo_settings(repo: str, request: Request, user: CurrentUser) -> RepoSettings:
    require_role(user, repo, min_role="mantenedor", request=request)
    with database.db_session() as conn:
        return database.clear_repo_settings(conn, repo)


@router.get("/repos/{repo:path}/role")
def my_role(repo: str, request: Request, user: CurrentUser) -> dict[str, str]:
    role = require_role(user, repo, min_role="revisor", request=request)
    return {"repo": repo, "role": role}


@router.get(
    "/repos/{repo:path}/ci-config",
    response_model=CiConfigOut,
    dependencies=[Depends(require_ingest_token)],
)
def get_ci_config(repo: str) -> CiConfigOut:
    """Configuración de este repo lista para que la Action la aplique
    (sin cookie de usuario -- mismo bearer token que `POST /api/scores`).

    `monthly_budget_tokens`/`max_diff_tokens` salen de los ajustes de LLM,
    que son de organización (no hay uno por repo todavía) -- ver
    `ensure_llm_settings` en db.py.
    """
    with database.db_session() as conn:
        settings = database.get_settings(conn, repo)
        llm = database.get_llm_settings(conn)
    return CiConfigOut(
        weights=settings.weights,
        thresholds=settings.thresholds,
        layers_enabled=settings.layers_enabled,
        block_on_high=settings.block_on_high,
        monthly_budget_tokens=llm.monthly_budget_tokens,
        max_diff_tokens=llm.max_diff_tokens,
    )


@router.post(
    "/scores",
    response_model=ScoreOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_ingest_token)],
)
def ingest_score(body: IngestScoreIn) -> ScoreOut:
    """Persistencia desde el adaptador CI (sin cookie de usuario)."""
    with database.db_session() as conn:
        score_id = database.insert_aggregated(conn, body.result, author_login=body.author_login)
        out = database.get_score(conn, score_id)
    if out is None:
        raise HTTPException(status_code=500, detail="No se pudo leer el score insertado")
    return out


def _monitored_repo_by_path(repo: str) -> MonitoredRepo | None:
    """La página de detalle de un repo (`RepoPage.tsx`) solo conoce su
    `repo_path` (viene de la URL, igual que `list_scores`/`my_role` de
    arriba) -- a diferencia de `routers/repos.py`, que gestiona repos por
    `id` de la organización que los administra. Sin acotar por org_id a
    propósito, mismo criterio que `pipeline.py::_load_repo_graph_context`:
    esto es solo para mostrar el mapa ya construido, no una decisión de
    control de acceso (esa la aplica `require_role` en cada endpoint de
    abajo)."""
    from watchgate.db.connection import get_session

    with next(get_session()) as session:
        return session.exec(select(MonitoredRepo).where(MonitoredRepo.repo_path == repo)).first()


@router.get("/repos/{repo:path}/knowledge-graph", response_model=RepoKnowledgeGraphOut)
def get_repo_knowledge_graph_by_path(repo: str, request: Request, user: CurrentUser) -> Any:
    """Mismo contrato que `routers/repos.py::get_repo_knowledge_graph`, pero
    localizado por `repo_path` (esta página no conoce el id de
    `MonitoredRepo`) -- ver ese endpoint para la respuesta `status="pending"`
    cuando el repo aún no tiene mapa construido."""
    require_role(user, repo, min_role="revisor", request=request)

    from watchgate.db.connection import get_session

    monitored_repo = _monitored_repo_by_path(repo)
    if monitored_repo is None:
        return RepoKnowledgeGraphOut(
            status="pending",
            error_message=None,
            overview="",
            project_type=None,
            languages=None,
            module_breakdown=[],
            node_count=0,
            edge_count=0,
            built_at=None,
            nodes=[],
        )

    with next(get_session()) as session:
        arch_summary = session.exec(
            select(RepoArchitectureSummary).where(
                RepoArchitectureSummary.monitored_repo_id == monitored_repo.id
            )
        ).first()
        if arch_summary is None:
            return RepoKnowledgeGraphOut(
                status="pending",
                error_message=None,
                overview="",
                project_type=None,
                languages=None,
                module_breakdown=[],
                node_count=0,
                edge_count=0,
                built_at=None,
                nodes=[],
            )

        nodes = session.exec(
            select(RepoGraphNode)
            .where(RepoGraphNode.monitored_repo_id == monitored_repo.id)
            .order_by(RepoGraphNode.file_path)
        ).all()

        return RepoKnowledgeGraphOut(
            status=arch_summary.status,
            error_message=arch_summary.error_message,
            overview=arch_summary.overview,
            project_type=arch_summary.project_type,
            languages=arch_summary.languages,
            module_breakdown=json.loads(arch_summary.module_breakdown_json or "[]"),
            node_count=arch_summary.node_count,
            edge_count=arch_summary.edge_count,
            built_at=arch_summary.built_at,
            nodes=[
                RepoGraphNodeOut(
                    file_path=n.file_path,
                    language=n.language,
                    category=n.category,
                    summary=n.summary,
                    symbols=json.loads(n.symbols or "[]"),
                    imports=json.loads(n.imports or "[]"),
                    loc=n.loc,
                )
                for n in nodes
            ],
        )


@router.post("/repos/{repo:path}/knowledge-graph/rebuild", status_code=status.HTTP_202_ACCEPTED)
def rebuild_repo_knowledge_graph_by_path(repo: str, request: Request, user: CurrentUser) -> Any:
    """Botón "Reconstruir mapa" desde la página de detalle del repo."""
    require_role(user, repo, min_role="mantenedor", request=request)

    monitored_repo = _monitored_repo_by_path(repo)
    if monitored_repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este repo todavía no está registrado en WatchGate.",
        )
    if monitored_repo.monitor_type == "git_server":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Los repos de servidor Git propio reconstruyen su mapa subiendo un "
                "snapshot nuevo (docker/git-server-hooks/upload_snapshot.sh)."
            ),
        )
    enqueued = _enqueue_repo_knowledge_graph(monitored_repo)
    return {"enqueued": enqueued, "repo_path": monitored_repo.repo_path}


class BlockedAuthorOut(BaseModel):
    author_login: str
    reason: str
    blocked_by: str
    blocked_at: datetime


class BlockAuthorIn(BaseModel):
    author_login: str
    reason: str = ""


@router.get("/repos/{repo:path}/blocked-authors", response_model=list[BlockedAuthorOut])
def list_blocked_authors(repo: str, request: Request, user: CurrentUser) -> Any:
    """Autores bloqueados de la organización que administra este repo --
    ver `core/pipeline.py::_check_blocked_author` para la comprobación real
    en cada análisis. El bloqueo es a nivel de organización, no de repo
    individual (un autor problemático en un repo probablemente lo es en
    todos), pero se gestiona desde la página de un repo concreto porque es
    donde normalmente se detecta el problema."""
    require_role(user, repo, min_role="revisor", request=request)

    monitored_repo = _monitored_repo_by_path(repo)
    if monitored_repo is None:
        return []

    from watchgate.db.connection import get_session

    with next(get_session()) as session:
        blocked = session.exec(
            select(BlockedAuthor)
            .where(BlockedAuthor.org_id == monitored_repo.org_id)
            .order_by(BlockedAuthor.blocked_at.desc())  # type: ignore[attr-defined]
        ).all()
        return [
            BlockedAuthorOut(
                author_login=b.author_login,
                reason=b.reason,
                blocked_by=b.blocked_by,
                blocked_at=b.blocked_at,
            )
            for b in blocked
        ]


@router.post(
    "/repos/{repo:path}/blocked-authors",
    response_model=BlockedAuthorOut,
    status_code=status.HTTP_201_CREATED,
)
def block_author(repo: str, body: BlockAuthorIn, request: Request, user: CurrentUser) -> Any:
    require_role(user, repo, min_role="mantenedor", request=request)

    monitored_repo = _monitored_repo_by_path(repo)
    if monitored_repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este repo todavía no está registrado en WatchGate.",
        )
    author_login = body.author_login.strip()
    if not author_login:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="author_login vacío")

    from watchgate.db.connection import get_session

    with next(get_session()) as session:
        existing = session.exec(
            select(BlockedAuthor).where(
                BlockedAuthor.org_id == monitored_repo.org_id,
                BlockedAuthor.author_login == author_login,
            )
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"'{author_login}' ya está bloqueado en esta organización.",
            )
        blocked = BlockedAuthor(
            id=str(uuid.uuid4()),
            org_id=monitored_repo.org_id,
            author_login=author_login,
            reason=body.reason.strip(),
            blocked_by=user.login,
            blocked_at=datetime.now(UTC),
        )
        session.add(blocked)
        session.commit()
        session.refresh(blocked)
        return BlockedAuthorOut(
            author_login=blocked.author_login,
            reason=blocked.reason,
            blocked_by=blocked.blocked_by,
            blocked_at=blocked.blocked_at,
        )


@router.delete("/repos/{repo:path}/blocked-authors/{author_login}", status_code=status.HTTP_200_OK)
def unblock_author(repo: str, author_login: str, request: Request, user: CurrentUser) -> Any:
    require_role(user, repo, min_role="mantenedor", request=request)

    monitored_repo = _monitored_repo_by_path(repo)
    if monitored_repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este repo todavía no está registrado en WatchGate.",
        )

    from watchgate.db.connection import get_session

    with next(get_session()) as session:
        existing = session.exec(
            select(BlockedAuthor).where(
                BlockedAuthor.org_id == monitored_repo.org_id,
                BlockedAuthor.author_login == author_login,
            )
        ).first()
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No estaba bloqueado."
            )
        session.delete(existing)
        session.commit()
    return {"unblocked": author_login}


@router.delete("/repos/{repo:path}")
def delete_repo_by_path(
    repo: str, request: Request, user: CurrentUser, session: DBSession
) -> dict[str, Any]:
    """Elimina TODOS los datos de un repo, en cualquier sitio del sistema
    donde vivan -- botón "Eliminar" de `/repos` en el frontend. Purga:

    - Histórico de `pr_scores` del Dashboard (`delete_scores_for_repo`).
    - `pr_scores` de la Engine DB (análisis vía Engine API/Action/agente
      para este `repo_path`, si los hay -- un repo puede tener historial
      ahí sin haber pasado nunca por "Auditoría Externa" del Dashboard).
    - `repo_settings` (umbrales/pesos propios de este repo, si los tenía).
    - `repo_roles`: TODOS los accesos concedidos sobre este repo, de
      cualquier usuario -- sin esto, si el mismo `repo_path` se vuelve a
      conectar más adelante, resucitarían permisos de la conexión
      anterior que nadie volvió a conceder.
    - Si además existe una fila `MonitoredRepo` para este `repo_path` en
      la organización del usuario actual: la propia fila, el mapa de
      conocimiento que le cuelga (`delete_monitored_repo_cascade` --
      FK sin `ON DELETE CASCADE`, el borrado en crudo reventaba con un
      500 opaco) y cualquier API key de agente atada a él (se REVOCAN y
      borran, no se bloquea el borrado por su culpa -- "eliminar todos
      los datos" incluye las credenciales que solo servían para acceder
      a ESTE repo; antes esto bloqueaba con 409 para no dejarlas
      huérfanas, pero orfandad y "seguir viva sin repo que la respalde"
      es justo el estado que un borrado completo debe evitar).

    Deliberadamente NO se tocan aquí `blocked_authors` (política de
    bloqueo de AUTORES a nivel de ORGANIZACIÓN, no de este repo -- otros
    repos de la misma organización siguen necesitándola) ni
    `VCSConnection` (la instalación de la GitHub App puede dar acceso a
    otros repos que siguen activos).

    `session` llega inyectado vía `Depends(get_db_session)` (mismo
    `DBSession` que usa `delete_external_repo`) en vez de abrir uno propio
    con `get_session()` a mano -- así comparte la sesión/engine de la
    petición y respeta `app.dependency_overrides` en tests (antes, al
    llamar a `get_session()` directamente, el override de sesión de test
    no tenía efecto y la consulta caía siempre sobre `default_engine`)."""
    require_role(user, repo, min_role="mantenedor", request=request)

    monitored_repo_deleted = False
    db_user = _get_or_create_db_user(session, normalize_login(user.login))
    org_id = db_user.org_id
    repo_row = session.exec(
        select(MonitoredRepo).where(MonitoredRepo.repo_path == repo, MonitoredRepo.org_id == org_id)
    ).first()

    engine_scores_deleted = session.execute(delete(PRScore).where(PRScore.repo == repo)).rowcount or 0

    with database.db_session() as conn:
        deleted_scores = database.delete_scores_for_repo(conn, repo)
        database.clear_repo_settings(conn, repo)
        database.delete_roles_for_repo(conn, repo)

    if repo_row is not None:
        bound_keys = session.exec(
            select(UserAPIKey).where(UserAPIKey.monitored_repo_id == repo_row.id)
        ).all()
        for key in bound_keys:
            session.delete(key)
        delete_monitored_repo_cascade(session, repo_row)
        session.commit()
        monitored_repo_deleted = True
    else:
        session.commit()

    return {
        "repo": repo,
        "scores_deleted": deleted_scores + engine_scores_deleted,
        "monitored_repo_deleted": monitored_repo_deleted,
    }
