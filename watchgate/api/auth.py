"""Middleware y dependencias de autenticación por API Key SHA-256 (wg_live_...)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from watchgate.api.dependencies import get_db_session
from watchgate.db.models import Organization, User, UserAPIKey
from watchgate.db.repository import verify_api_key

_bearer_security = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_user_from_api_key(
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_security)] = None,
    header_key: Annotated[str | None, Security(_api_key_header)] = None,
    session: Annotated[Session, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> tuple[UserAPIKey, User, Organization]:
    """Valida la API Key SHA-256 extraída del header Bearer o X-API-Key.

    Devuelve la tupla (UserAPIKey, User, Organization) si el token es válido y no ha expirado.
    Lanza HTTP 401 Unauthorized si falta el token o no es válido.
    """
    token: str | None = None
    if bearer and bearer.credentials:
        token = bearer.credentials.strip()
    elif header_key:
        token = header_key.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token Bearer o header X-API-Key para acceder a este recurso.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    verified = verify_api_key(session, token)
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida, no encontrada o expirada.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key, user, org = verified
    if not org:
        org = Organization(
            id="default-org", name="Default Organization", plan_tier="starter"
        )
    return api_key, user, org
