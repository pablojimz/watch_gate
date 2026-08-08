"""Middleware y dependencias de autenticación por API Key SHA-256 (wg_live_...)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from watchgate.api.dependencies import get_db_session
from watchgate.db.models import Organization, User, UserAPIKey
from watchgate.db.repository import create_organization, verify_api_key

_bearer_security = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Fallback para API keys sin organización propia (caso legado -- el
# Dashboard ya provisiona una Organización real por usuario, ver
# `dashboard/backend/routers/keys.py::_get_or_create_db_user`). Un ID fijo
# y conocido en vez de uno aleatorio para que sea idempotente entre
# peticiones y quede documentado qué claves comparten este cubo.
_FALLBACK_ORG_ID = "default-org"


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
        # Antes esto fabricaba un `Organization(...)` EN MEMORIA, nunca
        # persistido -- `QuotaService`/`PolicyService` vuelven a buscarla
        # por id (`get_organization(session, "default-org")`), que
        # devolvía `None` porque esa fila no existía nunca: la cuota caía
        # al valor por defecto sin aplicar de verdad y la gobernanza
        # corporativa se saltaba en silencio (`apply_policy_overrides`
        # trata `org=None` como "nada que aplicar"). `create_organization`
        # hace get-or-create por `org_id`, así que esto persiste la fila la
        # primera vez que hace falta y a partir de ahí `get_organization`
        # la encuentra de verdad -- cuota y gobernanza vuelven a aplicar,
        # aunque sea sobre un cubo compartido para claves sin organización
        # propia (caso legado, ver `_FALLBACK_ORG_ID`).
        org = create_organization(
            session, name="Default Organization", org_id=_FALLBACK_ORG_ID
        )
    return api_key, user, org


def _has_scope(api_key: UserAPIKey, required_scope: str) -> bool:
    granted = {s.strip() for s in (api_key.scopes or "").split(",") if s.strip()}
    return required_scope in granted


def require_scope(
    required_scope: str,
) -> Callable[..., tuple[UserAPIKey, User, Organization]]:
    """Fábrica de dependencia FastAPI: exige que la API key autenticada
    tenga `required_scope` entre los suyos, además de ser válida.

    `UserAPIKey.scopes` se define y se persiste desde que existe el modelo
    (`create_api_key`), pero nunca se leía en ningún punto de la
    autenticación -- `get_current_user_from_api_key` solo validaba hash y
    expiración. Cualquier API key válida, sea cual sea el scope con el que
    se emitió, podía llamar a cualquier endpoint: una clave pensada solo
    para lectura de resultados podía igualmente disparar `/analyze` o
    `/verify-fix` (que consumen presupuesto de tokens LLM, este último al
    doble coste).
    """

    def _dependency(
        auth: Annotated[
            tuple[UserAPIKey, User, Organization], Depends(get_current_user_from_api_key)
        ],
    ) -> tuple[UserAPIKey, User, Organization]:
        api_key, _user, _org = auth
        if not _has_scope(api_key, required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Esta API Key no tiene el scope '{required_scope}' requerido para "
                    "este recurso."
                ),
            )
        return auth

    return _dependency
