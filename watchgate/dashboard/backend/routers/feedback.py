"""feedback.py — endpoint de feedback humano + gestión de accesos (admin)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser, require_role
from watchgate.dashboard.backend.schemas import FeedbackIn, RepoRoleIn, RepoRoleOut, ScoreOut

router = APIRouter(tags=["feedback"])


@router.post("/scores/{score_id}/feedback", response_model=ScoreOut)
def submit_feedback(
    score_id: int, body: FeedbackIn, request: Request, user: CurrentUser
) -> ScoreOut:
    with database.db_session() as conn:
        existing = database.get_score(conn, score_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Score no encontrado")
        require_role(user, existing.repo, min_role="mantenedor", request=request)
        updated = database.set_feedback(conn, score_id, body.feedback)
    if updated is None:
        raise HTTPException(status_code=404, detail="Score no encontrado")
    return updated


@router.post("/scores/{score_id}/accept", response_model=ScoreOut)
def accept_score(score_id: int, request: Request, user: CurrentUser) -> ScoreOut:
    """Gate de aprobación manual: registra que `user` revisó este PR
    amarillo/rojo y decide seguir adelante a sabiendas del riesgo."""
    with database.db_session() as conn:
        existing = database.get_score(conn, score_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Score no encontrado")
        require_role(user, existing.repo, min_role="mantenedor", request=request)
        updated = database.set_accepted(conn, score_id, user.login)
    if updated is None:
        raise HTTPException(status_code=404, detail="Score no encontrado")
    return updated


@router.delete("/scores/{score_id}/accept", response_model=ScoreOut)
def unaccept_score(score_id: int, request: Request, user: CurrentUser) -> ScoreOut:
    with database.db_session() as conn:
        existing = database.get_score(conn, score_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Score no encontrado")
        require_role(user, existing.repo, min_role="mantenedor", request=request)
        updated = database.clear_accepted(conn, score_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Score no encontrado")
    return updated


@router.get("/admin/roles", response_model=list[RepoRoleOut])
def list_all_roles(request: Request, user: CurrentUser) -> list[RepoRoleOut]:
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere admin_organizacion",
            )
        rows = database.list_roles(conn)
    return [RepoRoleOut(user_login=r["user_login"], repo=r["repo"], role=r["role"]) for r in rows]


@router.put("/admin/roles", response_model=RepoRoleOut)
def upsert_role(body: RepoRoleIn, request: Request, user: CurrentUser) -> RepoRoleOut:
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere admin_organizacion",
            )
        database.upsert_role(conn, body.user_login, body.repo, body.role)
    return RepoRoleOut(user_login=body.user_login, repo=body.repo, role=body.role)


@router.delete("/admin/roles/{user_login}/{repo:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(user_login: str, repo: str, request: Request, user: CurrentUser) -> None:
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere admin_organizacion",
            )
        if not database.delete_role(conn, user_login, repo):
            raise HTTPException(status_code=404, detail="Rol no encontrado")
