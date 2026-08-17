"""Tests de watchgate/dashboard/backend/db.py: cuentas locales del
Dashboard (`dashboard_users` -- distinto de `repo_roles`, ver
routers/feedback.py::list_all_users) y la guarda contra dejar la
organización sin ningún `admin_organizacion` que pueda gestionar accesos.
"""

from __future__ import annotations

from pathlib import Path

from watchgate.dashboard.backend import db as database


def test_list_users_returns_created_accounts_sorted_by_login(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_user(conn, "beto", "correcto123", "Beto")
        database.upsert_user(conn, "ana", "correcto123", "Ana")

        logins = [u.login for u in database.list_users(conn)]

    assert logins == ["ana", "beto"]


def test_get_user_returns_none_for_unknown_login(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.get_user(conn, "no-existe") is None
        database.upsert_user(conn, "Carla", "correcto123", "Carla")
        # normalize_login: case-insensitive -- resuelto DENTRO del `with`,
        # accederlo fuera (sesión ya cerrada) lanza DetachedInstanceError
        # (expire_on_commit=True por defecto), ver el mismo hallazgo real
        # en routers/feedback.py::list_all_users.
        found_login = database.get_user(conn, "CARLA").login  # type: ignore[union-attr]

    assert found_login == "carla"


def test_delete_user_cascades_repo_roles(tmp_path: Path) -> None:
    """Borrar la cuenta local también borra sus roles asignados -- sin
    esto quedarían filas de repo_roles huérfanas, apuntando a un login
    que ya no puede autenticarse nunca."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_user(conn, "diego", "correcto123", "Diego")
        database.upsert_role(conn, "diego", "acme/payments-api", "revisor")
        database.upsert_role(conn, "diego", "acme/auth-service", "mantenedor")

        assert database.delete_user(conn, "DIEGO") is True

        assert database.get_user(conn, "diego") is None
        assert database.get_role(conn, "diego", "acme/payments-api") is None
        assert database.get_role(conn, "diego", "acme/auth-service") is None


def test_delete_user_returns_false_for_unknown_login(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.delete_user(conn, "no-existe") is False


def test_is_last_org_admin(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_role(conn, "unica", "acme/payments-api", "admin_organizacion")

        # Único admin_organizacion del sistema -- bloquea.
        assert database.is_last_org_admin(conn, "unica") is True
        # Alguien sin ese rol nunca es "el último admin" (no lo tiene).
        assert database.is_last_org_admin(conn, "nadie") is False

        # Con un segundo admin_organizacion, ninguno de los dos es "el
        # último" -- borrar cualquiera de los dos, en solitario, es seguro.
        database.upsert_role(conn, "otra", "acme/auth-service", "admin_organizacion")
        assert database.is_last_org_admin(conn, "unica") is False
        assert database.is_last_org_admin(conn, "otra") is False
