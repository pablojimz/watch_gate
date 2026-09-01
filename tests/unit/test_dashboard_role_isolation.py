"""Tests de aislamiento de roles del Dashboard (watchgate/dashboard/backend/db.py).

Se quitó el rol "admin_organizacion" del RBAC por completo -- ya no existe
ningún rol capaz de administrar una organización entera, solo
"mantenedor" (acotado de verdad por `(user_login, repo)` real vía
`get_role`) y "revisor". Este fichero fija esa garantía como tests
explícitos: que el rol ya no se puede ni persistir (CheckConstraint de la
tabla), que `user_is_org_admin()` (conservada por compatibilidad con sus
otros llamadores, ver su docstring) siempre devuelve `False`, y que el
auto-grant de `tasks.py` tras un escaneo sigue concediendo solo
"mantenedor" -- para que una regresión futura (alguien reintroduciendo
"admin_organizacion") falle aquí en vez de depender solo de descubrirlo
en auditoría."""

from __future__ import annotations

import pytest

from watchgate.dashboard.backend import db as database


def test_mantenedor_role_on_own_repo_does_not_grant_org_admin(tmp_path) -> None:
    """La forma correcta de "dale acceso a tu propio repo recién
    conectado" (lo que tasks.py hace) -- no convierte a nadie en admin de
    su organización, y mucho menos de otra."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_role(
            conn, "org-a-user", "orga/their-own-repo", "mantenedor", org_id="org-a"
        )

    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.user_is_org_admin(conn, "org-a-user", "org-a") is False
        assert database.get_role(conn, "org-a-user", "orga/their-own-repo") == "mantenedor"
        # Sin rol en el repo de OTRA organización, y sin ser admin de
        # ninguna, no hay forma de leerlo.
        assert database.get_role(conn, "org-a-user", "orgb/victim-repo") is None


def test_admin_organizacion_role_is_rejected_by_the_database(tmp_path) -> None:
    """`admin_organizacion` ya no es un valor válido de `RepoRole.role` --
    el CheckConstraint de la tabla lo rechaza, no solo la validación de la
    API (`RoleName` en schemas.py)."""
    with pytest.raises(Exception):  # noqa: B017 -- IntegrityError de SQLAlchemy, sin importar el driver
        with database.db_session(tmp_path / "dashboard.db") as conn:
            database.upsert_role(conn, "somebody", "orga/some-repo", "admin_organizacion")  # type: ignore[arg-type]


def test_user_is_org_admin_always_returns_false(tmp_path) -> None:
    """`user_is_org_admin()` se conserva (muchos llamadores fuera del
    propio Dashboard -- agent_access.py, mcp/tools.py,
    db/repository.py::check_user_repo_permission -- ya degradan
    correctamente cuando esto es `False`) pero ya no hay ningún camino
    real para que devuelva `True`: ni con rol de mantenedor en el repo, ni
    con `org_id=None`."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_role(conn, "org-a-user", "orga/some-repo", "mantenedor", org_id="org-a")

    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.user_is_org_admin(conn, "org-a-user", "org-a") is False
        assert database.user_is_org_admin(conn, "org-a-user", "org-b") is False
        assert database.user_is_org_admin(conn, "org-a-user", None) is False


def test_run_scan_role_grant_never_uses_admin_organizacion() -> None:
    """Red de seguridad a nivel de fuente: el auto-grant de tasks.py tras
    un escaneo nunca debe volver a conceder "admin_organizacion" -- si
    alguien lo reintroduce (aunque sea copiando/pegando una línea
    antigua), este test falla inmediato en vez de depender solo de
    descubrirlo en auditoría."""
    import inspect

    from watchgate.dashboard.backend import tasks

    for func in (tasks.run_managed_scan, tasks.run_main_branch_scan, tasks.run_audit_scan):
        source = inspect.getsource(func)
        assert 'upsert_role(dash_conn, user_obj.name, repo_path, "admin_organizacion")' not in (
            source
        ), f"{func.__name__} concede admin_organizacion -- ver auditoría"
        assert 'upsert_role(dash_conn, user_obj.name, repo_path, "mantenedor")' in source, (
            f"{func.__name__} debería seguir concediendo mantenedor tras el escaneo"
        )
