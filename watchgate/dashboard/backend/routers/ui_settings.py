"""ui_settings.py — apariencia del dashboard (colores / diseño)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.org_scope import is_site_superadmin
from watchgate.dashboard.backend.schemas import UiSettings

router = APIRouter(prefix="/settings/ui", tags=["ui"])


@router.get("", response_model=UiSettings)
def get_ui_settings(user: CurrentUser) -> UiSettings:
    with database.db_session() as conn:
        return database.get_ui_settings(conn)


@router.put("", response_model=UiSettings)
def put_ui_settings(body: UiSettings, user: CurrentUser) -> UiSettings:
    # Auditoría: branding/apariencia es una fila SINGLETON compartida por
    # TODA la instancia (get_ui_settings/set_ui_settings, sin `repo`/
    # `org_id` en ningún sitio) -- no es un dato por-organización, así que
    # ya no basta con `admin_organizacion` (ahora acotado por org) --
    # exige superadmin de sitio (ver org_scope.py).
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )
    with database.db_session() as conn:
        return database.set_ui_settings(conn, body)
