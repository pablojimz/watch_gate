"""Tests de watchgate/dashboard/backend/auth.py (spec §13): arranque seguro.

Cubre `ensure_safe_startup_config`, la comprobación que se niega a levantar
el dashboard con dev mode desactivado y el secreto de sesión todavía en su
valor por defecto público (`INSECURE_DEFAULT_SECRET`) -- sin esto, un
despliegue real que olvidase fijar `WATCHGATE_DASHBOARD_SECRET` firmaría
cookies de sesión forjables por cualquiera que haya leído el repo.
"""

from __future__ import annotations

import pytest

from watchgate.dashboard.backend.auth import (
    INSECURE_DEFAULT_SECRET,
    ensure_safe_startup_config,
)


def test_refuses_to_start_with_default_secret_and_dev_mode_off(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")
    monkeypatch.delenv("WATCHGATE_DASHBOARD_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="WATCHGATE_DASHBOARD_SECRET"):
        ensure_safe_startup_config()


def test_refuses_to_start_with_explicit_insecure_default_and_dev_mode_off(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SECRET", INSECURE_DEFAULT_SECRET)
    with pytest.raises(RuntimeError):
        ensure_safe_startup_config()


def test_starts_with_dev_mode_off_and_a_real_secret(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_DEV_MODE", "0")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SECRET", "un-secreto-real-de-produccion")
    ensure_safe_startup_config()  # no debe lanzar


def test_default_secret_is_allowed_while_dev_mode_stays_on(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_DASHBOARD_DEV_MODE", raising=False)  # default "1"
    monkeypatch.delenv("WATCHGATE_DASHBOARD_SECRET", raising=False)
    ensure_safe_startup_config()  # no debe lanzar: es la comodidad de dev local
