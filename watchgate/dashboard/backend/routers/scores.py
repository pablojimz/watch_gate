"""scores.py — endpoints de histórico de puntuaciones y repos visibles."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import select

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser, require_ingest_token, require_role
from watchgate.dashboard.backend.routers.repos import _enqueue_repo_knowledge_graph
from watchgate.dashboard.backend.schemas import CiConfigOut, IngestScoreIn, RepoSettings, ScoreOut
from watchgate.db.models import MonitoredRepo, RepoArchitectureSummary, RepoGraphNode

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
    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user.login)
        return database.list_repos_for_user(conn, user.login, is_admin=is_admin)


@router.get("/repos/{repo:path}/scores", response_model=list[ScoreOut])
def list_scores(repo: str, request: Request, user: CurrentUser) -> list[ScoreOut]:
    require_role(user, repo, min_role="revisor", request=request)
    with database.db_session() as conn:
        return database.list_scores(conn, repo)


@router.get("/settings/defaults", response_model=RepoSettings)
def get_default_settings(_user: CurrentUser) -> RepoSettings:
    with database.db_session() as conn:
        return database.get_org_settings(conn)


@router.put("/settings/defaults", response_model=RepoSettings)
def put_default_settings(body: RepoSettings, user: CurrentUser) -> RepoSettings:
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere admin")
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
    require_role(user, repo, min_role="admin_organizacion", request=request)
    with database.db_session() as conn:
        return database.set_settings(conn, repo, body)


@router.delete("/repos/{repo:path}/settings", response_model=RepoSettings)
def reset_repo_settings(repo: str, request: Request, user: CurrentUser) -> RepoSettings:
    require_role(user, repo, min_role="admin_organizacion", request=request)
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
