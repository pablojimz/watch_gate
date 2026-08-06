"""scores.py — endpoints de histórico de puntuaciones y repos visibles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser, require_ingest_token, require_role
from watchgate.dashboard.backend.schemas import IngestScoreIn, RepoSettings, ScoreOut

router = APIRouter(tags=["scores"])


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


@router.post(
    "/scores",
    response_model=ScoreOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_ingest_token)],
)
def ingest_score(body: IngestScoreIn) -> ScoreOut:
    """Persistencia desde el adaptador CI (sin cookie de usuario)."""
    with database.db_session() as conn:
        score_id = database.insert_aggregated(
            conn, body.result, author_login=body.author_login
        )
        out = database.get_score(conn, score_id)
    if out is None:
        raise HTTPException(status_code=500, detail="No se pudo leer el score insertado")
    return out
