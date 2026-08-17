"""user_settings.py — ajuste de configuración personal / perfil de usuario (accesible a todos)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import UserSettingsIn, UserSettingsOut

router = APIRouter(prefix="/settings/user", tags=["user_settings"])


@router.get("", response_model=UserSettingsOut)
def get_user_settings(user: CurrentUser) -> UserSettingsOut:
    with database.db_session() as conn:
        try:
            return database.get_user_settings(conn, user.login)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("", response_model=UserSettingsOut)
def put_user_settings(body: UserSettingsIn, user: CurrentUser) -> UserSettingsOut:
    with database.db_session() as conn:
        try:
            return database.set_user_settings(conn, user.login, body)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
