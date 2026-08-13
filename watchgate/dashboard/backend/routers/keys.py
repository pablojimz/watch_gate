"""keys.py — Endpoints del Dashboard para la gestión de API Keys por usuario (Tarea 5.1)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import normalize_login
from watchgate.db.connection import get_db_session
from watchgate.db.models import MonitoredRepo
from watchgate.db.models import User as DBUser
from watchgate.db.models import UserAPIKey
from watchgate.db.repository import create_api_key, create_organization, create_user

DBSession = Annotated[Session, Depends(get_db_session)]

router = APIRouter(prefix="/keys", tags=["keys"])


class CreateKeyRequest(BaseModel):
    name: str = Field(default="API Key", description="Nombre descriptivo de la clave")
    scopes: str = Field(
        default="analysis:write,scores:read",
        description="Permisos asignados separados por comas",
    )
    is_test: bool = Field(default=False, description="Si es una clave de prueba wg_test_...")
    # Sin valor por defecto: toda clave NUEVA debe crearse atada a un repo
    # concreto -- ya no se permite crear claves generales de organización.
    # Si el cliente no lo manda, FastAPI ya responde 422 antes de llegar a
    # create_key().
    monitored_repo_id: str = Field(
        description="ID del MonitoredRepo (de la organización del usuario) al que queda atada la clave"
    )


class KeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: str
    created_at: str
    expires_at: str | None = None
    last_used_at: str | None = None
    monitored_repo_id: str | None = None
    repo_path: str | None = None  # Resuelto para mostrar, None si es clave legado


class CreatedKeyResponse(KeyResponse):
    raw_token: str = Field(
        description="Token secreto crudo wg_live_... Muestra solo una vez al crear."
    )


def _get_or_create_db_user(session: Session, user_login: str) -> DBUser:
    """Asegura que el usuario autenticado del Dashboard exista en el esquema SQLModel DB,
    con una Organización PERSISTIDA propia (multi-tenant real).

    `current_user.login` ya llega normalizado desde la cookie de sesión
    (`create_session_token`), pero se normaliza también aquí -- este email
    sintético es la clave de identidad de un esquema de usuarios aparte
    (watchgate/db/, el de la Engine API), y no debería depender de que la
    normalización de la sesión nunca cambie para seguir siendo correcto.

    Antes, este era el ÚNICO punto real que crea usuarios/API keys desde el
    Dashboard y nunca pasaba `org_id` -- `verify_api_key` (auth.py) caía
    entonces a un `Organization(id="default-org", ...)` fabricado EN
    MEMORIA (nunca persistido). Resultado: todas las claves creadas desde
    el Dashboard compartían el mismo cubo sintético "default-org" --
    consumo de tokens de un cliente contando contra la cuota de todos los
    demás, y la gobernanza corporativa (`policy_json`) nunca aplicándose
    (`PolicyService.apply_policy_overrides` se salta si `org` es `None`,
    que es justo lo que devolvía `get_organization("default-org")` al no
    existir esa fila). Ahora cada usuario obtiene su propia Organización
    real, con `org_id` determinista (`personal-<user_id>`) para que
    llamadas repetidas sean idempotentes y no creen duplicados.
    """
    normalized = normalize_login(user_login)
    email = f"{normalized}@watchgate.internal"
    user = create_user(session, email=email, name=normalized)

    if not user.org_id:
        personal_org_id = f"personal-{user.id}"
        org = create_organization(session, name=f"{normalized} (personal)", org_id=personal_org_id)
        user.org_id = org.id
        session.add(user)
        session.commit()
        session.refresh(user)

    return user


@router.post("", response_model=CreatedKeyResponse, status_code=status.HTTP_201_CREATED)
def create_key(
    body: CreateKeyRequest,
    current_user: CurrentUser,
    session: DBSession,
) -> dict[str, Any]:
    """Genera una nueva API Key para el usuario autenticado, atada
    obligatoriamente a un repo de su propia organización."""
    db_user = _get_or_create_db_user(session, current_user.login)

    repo = session.get(MonitoredRepo, body.monitored_repo_id)
    if repo is None or repo.org_id != db_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El repo no existe o no pertenece a tu organización.",
        )

    api_key, raw_token = create_api_key(
        session=session,
        user_id=db_user.id,
        name=body.name,
        scopes=body.scopes,
        is_test=body.is_test,
        org_id=db_user.org_id,
        monitored_repo_id=repo.id,
    )

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "created_at": api_key.created_at.isoformat(),
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "last_used_at": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
        "monitored_repo_id": api_key.monitored_repo_id,
        "repo_path": repo.repo_path,
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

    # Resuelve repo_path en lote (evita N+1 si el usuario tiene muchas claves).
    repo_ids = {k.monitored_repo_id for k in keys if k.monitored_repo_id}
    repos_by_id: dict[str, str] = {}
    if repo_ids:
        repo_stmt = select(MonitoredRepo).where(MonitoredRepo.id.in_(repo_ids))  # type: ignore[attr-defined]
        repos_by_id = {r.id: r.repo_path for r in session.exec(repo_stmt).all()}

    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": k.scopes,
            "created_at": k.created_at.isoformat(),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "monitored_repo_id": k.monitored_repo_id,
            "repo_path": repos_by_id.get(k.monitored_repo_id) if k.monitored_repo_id else None,
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
