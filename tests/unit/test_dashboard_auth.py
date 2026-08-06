"""Tests de watchgate/dashboard/backend/auth.py (spec §13): arranque seguro.

Cubre `ensure_safe_startup_config` (se niega a levantar el dashboard con dev
mode desactivado si el secreto de sesión sigue en `INSECURE_DEFAULT_SECRET`
o si falta el token de ingesta) y `require_ingest_token`, la autenticación
de `POST /api/scores` (la Action no tiene cookie de sesión de usuario).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from watchgate.dashboard.backend.auth import (
    INSECURE_DEFAULT_SECRET,
    ensure_safe_startup_config,
    require_ingest_token,
)


def _request_with_auth_header(value: str | None) -> Request:
    headers = [(b"authorization", value.encode())] if value is not None else []
    scope = {"type": "http", "headers": headers}
    return Request(scope)


def test_refuses_to_start_with_default_secret_and_dev_mode_off(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "some-token")
    monkeypatch.delenv("WATCHGATE_DASHBOARD_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="WATCHGATE_DASHBOARD_SECRET"):
        ensure_safe_startup_config()


def test_refuses_to_start_with_explicit_insecure_default_and_dev_mode_off(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "some-token")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SECRET", INSECURE_DEFAULT_SECRET)
    with pytest.raises(RuntimeError):
        ensure_safe_startup_config()


def test_refuses_to_start_without_ingest_token_and_dev_mode_off(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SECRET", "un-secreto-real-de-produccion")
    monkeypatch.delenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="WATCHGATE_DASHBOARD_INGEST_TOKEN"):
        ensure_safe_startup_config()


def test_starts_with_dev_mode_off_and_real_secret_and_ingest_token(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SECRET", "un-secreto-real-de-produccion")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "un-token-real")
    ensure_safe_startup_config()  # no debe lanzar


def test_default_secret_is_allowed_while_dev_mode_stays_on(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_DASHBOARD_DEV_MODE", raising=False)  # default "1"
    monkeypatch.delenv("WATCHGATE_DASHBOARD_SECRET", raising=False)
    monkeypatch.delenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", raising=False)
    ensure_safe_startup_config()  # no debe lanzar: es la comodidad de dev local


def test_ingest_token_open_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", raising=False)
    require_ingest_token(_request_with_auth_header(None))  # no debe lanzar


def test_ingest_token_rejects_missing_header_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "secreto-ci")
    with pytest.raises(HTTPException) as exc_info:
        require_ingest_token(_request_with_auth_header(None))
    assert exc_info.value.status_code == 401


def test_ingest_token_rejects_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "secreto-ci")
    with pytest.raises(HTTPException):
        require_ingest_token(_request_with_auth_header("Bearer token-incorrecto"))


def test_ingest_token_accepts_correct_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "secreto-ci")
    require_ingest_token(_request_with_auth_header("Bearer secreto-ci"))  # no debe lanzar
