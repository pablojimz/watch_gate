"""keys.py — Endpoints del Dashboard para la gestión de API Keys por usuario (Tarea 5.1)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import normalize_login
from watchgate.db.connection import get_db_session
from watchgate.db.models import User as DBUser
from watchgate.db.models import UserAPIKey
from watchgate.db.repository import create_api_key, create_user

DBSession = Annotated[Session, Depends(get_db_session)]

router = APIRouter(prefix="/keys", tags=["keys"])


class CreateKeyRequest(BaseModel):
    name: str = Field(default="API Key", description="Nombre descriptivo de la clave")
    scopes: str = Field(
        default="analysis:write,scores:read",
        description="Permisos asignados separados por comas",
    )
    is_test: bool = Field(default=False, description="Si es una clave de prueba wg_test_...")


class KeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: str
    created_at: str
    expires_at: str | None = None
    last_used_at: str | None = None


class CreatedKeyResponse(KeyResponse):
    raw_token: str = Field(
        description="Token secreto crudo wg_live_... Muestra solo una vez al crear."
    )


def _get_or_create_db_user(session: Session, user_login: str) -> DBUser:
    """Asegura que el usuario autenticado del Dashboard exista en el esquema SQLModel DB.

    `current_user.login` ya llega normalizado desde la cookie de sesión
    (`create_session_token`), pero se normaliza también aquí -- este email
    sintético es la clave de identidad de un esquema de usuarios aparte
    (watchgate/db/, el de la Engine API), y no debería depender de que la
    normalización de la sesión nunca cambie para seguir siendo correcto.
    """
    normalized = normalize_login(user_login)
    email = f"{normalized}@watchgate.internal"
    return create_user(session, email=email, name=normalized)


@router.post("", response_model=CreatedKeyResponse, status_code=status.HTTP_201_CREATED)
def create_key(
    body: CreateKeyRequest,
    current_user: CurrentUser,
    session: DBSession,
) -> dict[str, Any]:
    """Genera una nueva API Key para el usuario autenticado."""
    db_user = _get_or_create_db_user(session, current_user.login)

    api_key, raw_token = create_api_key(
        session=session,
        user_id=db_user.id,
        name=body.name,
        scopes=body.scopes,
        is_test=body.is_test,
    )

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "created_at": api_key.created_at.isoformat(),
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "last_used_at": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
        "raw_token": raw_token,
    }


@router.get("", response_model=list[KeyResponse])
def list_keys(
    current_user: CurrentUser,
    session: DBSession,
) -> list[dict[str, Any]]:
    """Obtiene la lista de API Keys pertenecientes al usuario actual."""
    db_user = _get_or_create_db_user(session, current_user.login)

    stmt = select(UserAPIKey).where(UserAPIKey.user_id == db_user.id)
    keys = session.exec(stmt).all()

    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": k.scopes,
            "created_at": k.created_at.isoformat(),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.delete("/{key_id}")
def delete_key(
    key_id: str,
    current_user: CurrentUser,
    session: DBSession,
) -> dict[str, str]:
    """Revoca/elimina una API Key del usuario."""
    db_user = _get_or_create_db_user(session, current_user.login)

    stmt = select(UserAPIKey).where(UserAPIKey.id == key_id, UserAPIKey.user_id == db_user.id)
    key_record = session.exec(stmt).first()

    if not key_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API Key con ID '{key_id}' no encontrada.",
        )

    session.delete(key_record)
    session.commit()

    return {"status": "deleted", "id": key_id}
