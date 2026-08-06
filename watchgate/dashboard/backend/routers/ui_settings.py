"""ui_settings.py — apariencia del dashboard (colores / diseño)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import UiSettings

router = APIRouter(prefix="/settings/ui", tags=["ui"])


@router.get("", response_model=UiSettings)
def get_ui_settings(user: CurrentUser) -> UiSettings:
    with database.db_session() as conn:
        return database.get_ui_settings(conn)


@router.put("", response_model=UiSettings)
def put_ui_settings(body: UiSettings, user: CurrentUser) -> UiSettings:
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere admin")
        return database.set_ui_settings(conn, body)
