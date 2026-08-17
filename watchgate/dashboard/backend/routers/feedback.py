"""feedback.py — endpoint de feedback humano + gestión de accesos (admin)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser, require_role
from watchgate.dashboard.backend.schemas import (
    DashboardUserCreate,
    DashboardUserOut,
    FeedbackIn,
    RepoRoleIn,
    RepoRoleOut,
    RoleName,
    ScoreOut,
    normalize_login,
)

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
    return [
        RepoRoleOut(user_login=r["user_login"], repo=r["repo"], role=cast(RoleName, r["role"]))
        for r in rows
    ]


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


@router.get("/admin/users", response_model=list[DashboardUserOut])
def list_all_users(request: Request, user: CurrentUser) -> list[DashboardUserOut]:
    """Cuentas locales (login/contraseña) del Dashboard -- distinto de
    `/admin/roles`: esto es la cuenta en sí (puede iniciar sesión con
    usuario/contraseña), aquello es qué repos puede ver/administrar una
    vez dentro. Un login puede tener roles asignados sin tener cuenta
    local aquí (entra por GitHub/OIDC) -- las dos tablas son
    independientes a propósito."""
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere admin_organizacion",
            )
        users = database.list_users(conn)
        # Construir los DTOs DENTRO del `with`: `conn.close()` al salir
        # expira los objetos ORM (`expire_on_commit=True` por defecto), y
        # acceder a `.login`/`.display_name` después lanza
        # `DetachedInstanceError` -- reproducido en la revisión (mismo
        # motivo por el que `list_roles()` en db.py ya devuelve dicts en
        # vez de instancias ORM).
        return [DashboardUserOut(login=u.login, display_name=u.display_name) for u in users]


@router.post("/admin/users", response_model=DashboardUserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: DashboardUserCreate, request: Request, user: CurrentUser) -> DashboardUserOut:
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere admin_organizacion",
            )
        if database.get_user(conn, body.login) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una cuenta local con el login '{body.login}'",
            )
        database.upsert_user(conn, body.login, body.password, body.display_name)
    return DashboardUserOut(login=body.login, display_name=body.display_name)


@router.delete("/admin/users/{login}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(login: str, request: Request, user: CurrentUser) -> None:
    """Borra la cuenta local y, en cascada, todos sus roles asignados
    (`database.delete_user`). Dos guardas contra dejar la organización sin
    forma de gestionarse: no se puede borrar la propia cuenta desde aquí
    (evita un auto-bloqueo accidental), ni la del único
    `admin_organizacion` que quede."""
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere admin_organizacion",
            )
        if normalize_login(login) == normalize_login(user.login):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes eliminar tu propia cuenta",
            )
        if database.is_last_org_admin(conn, login):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar al único admin_organizacion restante",
            )
        if not database.delete_user(conn, login):
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
