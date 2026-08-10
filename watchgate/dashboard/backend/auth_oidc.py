"""auth_oidc.py — segunda vía OIDC genérica (Auth0/Keycloak).

Produce la misma cookie de sesión que el flujo GitHub, de modo que el resto
del backend no distingue cómo se autenticó el usuario.
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request, Response, status

from watchgate.dashboard.backend.auth import (
    _frontend_origin,
    create_session_token,
    set_session_cookie,
)

router = APIRouter(prefix="/auth/oidc", tags=["auth-oidc"])

oauth = OAuth()


def _configured() -> bool:
    return bool(
        os.environ.get("WATCHGATE_OIDC_CLIENT_ID")
        and os.environ.get("WATCHGATE_OIDC_CLIENT_SECRET")
        and os.environ.get("WATCHGATE_OIDC_ISSUER")
    )


def setup_oidc() -> None:
    if not _configured():
        return
    oauth.register(
        name="oidc",
        client_id=os.environ["WATCHGATE_OIDC_CLIENT_ID"],
        client_secret=os.environ["WATCHGATE_OIDC_CLIENT_SECRET"],
        server_metadata_url=(
            os.environ["WATCHGATE_OIDC_ISSUER"].rstrip("/") + "/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid profile email"},
    )


@router.get("/login")
async def oidc_login(request: Request) -> Response:
    if not _configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OIDC no configurado (WATCHGATE_OIDC_*)",
        )
    redirect_uri = os.environ.get(
        "WATCHGATE_OIDC_REDIRECT_URI",
        "http://localhost:8000/api/auth/oidc/callback",
    )
    client = oauth.create_client("oidc")
    res: Response = await client.authorize_redirect(request, redirect_uri)
    return res


@router.get("/callback")
async def oidc_callback(request: Request, response: Response) -> Response:
    if not _configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OIDC no configurado",
        )
    client = oauth.create_client("oidc")
    token = await client.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    login = (
        userinfo.get("preferred_username")
        or userinfo.get("nickname")
        or userinfo.get("email")
        or userinfo.get("sub")
    )
    if not login:
        raise HTTPException(status_code=400, detail="OIDC no devolvió identificador de usuario")

    session = create_session_token(str(login))
    set_session_cookie(response, session)
    response.status_code = status.HTTP_307_TEMPORARY_REDIRECT
    response.headers["Location"] = f"{_frontend_origin()}/repos"
    return response
