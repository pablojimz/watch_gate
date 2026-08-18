"""user_settings.py — ajuste de configuración personal / perfil de usuario (accesible a todos)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import ChangePasswordIn, UserSettingsIn, UserSettingsOut

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


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(body: ChangePasswordIn, user: CurrentUser) -> None:
    """Cambia la contraseña de la cuenta local propia -- exige la
    contraseña actual (decisión explícita del equipo, 2026-08-17: proteger
    el cambio aunque la sesión ya esté autenticada, por si alguien se deja
    la sesión abierta). Solo aplica a cuentas locales (login/contraseña) --
    `get_user_settings` (arriba) ya 404 si `user.login` no tiene fila en
    `dashboard_users`, así que llegar hasta aquí ya implica que existe."""
    with database.db_session() as conn:
        existing = database.get_user(conn, user.login)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta cuenta no tiene contraseña local (inicias sesión con GitHub/OIDC).",
            )
        if not database.verify_password(body.current_password, existing.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña actual incorrecta"
            )
        database.change_password(conn, user.login, body.new_password)
