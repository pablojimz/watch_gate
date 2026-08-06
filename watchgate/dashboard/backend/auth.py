"""auth.py — OAuth GitHub + cookie de sesión firmada + resolución de rol."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.schemas import DevLoginIn, PasswordLoginIn, RoleName, User

SESSION_COOKIE = "watchgate_session"
ROLE_RANK: dict[RoleName, int] = {
    "revisor": 1,
    "mantenedor": 2,
    "admin_organizacion": 3,
}

router = APIRouter(prefix="/auth", tags=["auth"])


def _secret() -> str:
    return os.environ.get("WATCHGATE_DASHBOARD_SECRET", "dev-insecure-secret-change-me")


def _frontend_origin() -> str:
    return os.environ.get("WATCHGATE_DASHBOARD_FRONTEND_ORIGIN", "http://localhost:5173")


def _github_client_id() -> str | None:
    return os.environ.get("WATCHGATE_GITHUB_CLIENT_ID")


def _github_client_secret() -> str | None:
    return os.environ.get("WATCHGATE_GITHUB_CLIENT_SECRET")


def _dev_mode() -> bool:
    return os.environ.get("WATCHGATE_DASHBOARD_DEV_MODE", "1") == "1"


def create_session_token(login: str, github_token: str | None = None) -> str:
    payload: dict[str, object] = {
        "sub": login,
        "exp": datetime.now(UTC) + timedelta(days=7),
    }
    if github_token:
        payload["gh"] = github_token
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_session_token(token: str) -> dict[str, object]:
    return jwt.decode(token, _secret(), algorithms=["HS256"])


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("WATCHGATE_DASHBOARD_SECURE_COOKIE", "0") == "1",
        max_age=7 * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def get_current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    try:
        payload = decode_session_token(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida"
        ) from exc
    login = payload.get("sub")
    if not isinstance(login, str) or not login:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    return User(login=login)


CurrentUser = Annotated[User, Depends(get_current_user)]


def _github_token_from_request(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        payload = decode_session_token(token)
    except JWTError:
        return None
    gh = payload.get("gh")
    return gh if isinstance(gh, str) else None


def resolve_role(user_login: str, repo: str, github_token: str | None = None) -> RoleName:
    """Resuelve el rol: fila en repo_roles, o inferencia desde GitHub Collaborators API."""
    with database.db_session() as conn:
        if database.user_is_org_admin(conn, user_login):
            return "admin_organizacion"
        existing = database.get_role(conn, user_login, repo)
        if existing is not None:
            return existing

    if github_token and "/" in repo:
        owner, name = repo.split("/", 1)
        permission = _fetch_github_permission(github_token, owner, name, user_login)
        if permission is not None:
            mapped = _map_github_permission(permission)
            with database.db_session() as conn:
                database.upsert_role(conn, user_login, repo, mapped)
            return mapped

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Sin rol asignado en {repo}",
    )


def _map_github_permission(permission: str) -> RoleName:
    if permission in {"admin", "maintain", "write"}:
        return "mantenedor"
    return "revisor"


def _fetch_github_permission(token: str, owner: str, repo: str, user_login: str) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/collaborators/{user_login}/permission"
    try:
        response = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15.0,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    perm = data.get("permission")
    return perm if isinstance(perm, str) else None


def require_role(
    user: User,
    repo: str,
    min_role: RoleName,
    request: Request | None = None,
) -> RoleName:
    github_token = _github_token_from_request(request) if request is not None else None
    role = resolve_role(user.login, repo, github_token=github_token)
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Se requiere rol ≥ {min_role}",
        )
    return role


@router.get("/github/login")
def github_login() -> Response:
    client_id = _github_client_id()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="WATCHGATE_GITHUB_CLIENT_ID no configurado",
        )
    redirect_uri = os.environ.get(
        "WATCHGATE_GITHUB_REDIRECT_URI",
        "http://localhost:8000/api/auth/github/callback",
    )
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={client_id}&scope=read:org,repo&redirect_uri={redirect_uri}"
    )
    return Response(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": url})


@router.get("/github/callback")
def github_callback(code: str, response: Response) -> Response:
    client_id = _github_client_id()
    client_secret = _github_client_secret()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Credenciales GitHub OAuth no configuradas",
        )

    token_resp = httpx.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        timeout=15.0,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No se obtuvo access_token de GitHub")

    user_resp = httpx.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15.0,
    )
    user_resp.raise_for_status()
    login = user_resp.json()["login"]

    session = create_session_token(login, github_token=access_token)
    set_session_cookie(response, session)
    response.status_code = status.HTTP_307_TEMPORARY_REDIRECT
    response.headers["Location"] = f"{_frontend_origin()}/repos"
    return response


@router.post("/login")
def password_login(body: PasswordLoginIn, response: Response) -> dict[str, str]:
    """Login local con usuario/contraseña (independiente de GitHub/GitLab)."""
    with database.db_session() as conn:
        ok = database.authenticate_user(conn, body.username, body.password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    token = create_session_token(body.username)
    set_session_cookie(response, token)
    return {"login": body.username}


@router.post("/dev-login")
def dev_login(body: DevLoginIn, response: Response) -> dict[str, str]:
    """Login de desarrollo (solo si WATCHGATE_DASHBOARD_DEV_MODE=1)."""
    if not _dev_mode():
        raise HTTPException(status_code=404, detail="Dev login deshabilitado")

    with database.db_session() as conn:
        # Asegura que el usuario de demo tenga al menos un rol visible.
        repos = database.list_repos_for_user(
            conn, body.login, is_admin=body.role == "admin_organizacion"
        )
        if not repos:
            database.upsert_role(conn, body.login, "acme/payments-api", body.role)
            if body.role == "admin_organizacion":
                database.upsert_role(conn, body.login, "acme/auth-service", body.role)
        elif body.role == "admin_organizacion":
            for repo in repos or ["acme/payments-api"]:
                database.upsert_role(conn, body.login, repo, body.role)
        else:
            database.upsert_role(conn, body.login, repos[0], body.role)

    token = create_session_token(body.login)
    set_session_cookie(response, token)
    return {"login": body.login, "role": body.role}


@router.get("/me")
def me(user: CurrentUser, request: Request) -> dict[str, object]:
    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user.login)
        repos = database.list_repos_for_user(conn, user.login, is_admin=is_admin)
    return {"login": user.login, "is_admin": is_admin, "repos": repos}


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}
