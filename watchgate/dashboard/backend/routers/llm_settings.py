"""llm_settings.py — configuración de proveedores / modelos LLM (admin)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import LlmSettingsIn, LlmSettingsOut

router = APIRouter(prefix="/settings/llm", tags=["llm"])


def _require_admin(user: CurrentUser) -> None:
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere admin")


@router.get("", response_model=LlmSettingsOut)
def get_llm_settings(user: CurrentUser) -> LlmSettingsOut:
    _require_admin(user)
    with database.db_session() as conn:
        return database.get_llm_settings(conn)


@router.put("", response_model=LlmSettingsOut)
def put_llm_settings(body: LlmSettingsIn, user: CurrentUser) -> LlmSettingsOut:
    _require_admin(user)
    with database.db_session() as conn:
        return database.set_llm_settings(conn, body)
