"""Tests de aislamiento de roles del Dashboard (watchgate/dashboard/backend/db.py).

Auditoría (hallazgo crítico, corregido en dos capas):

1. `tasks.py` (run_managed_scan/run_main_branch_scan/run_audit_scan)
   concedía "admin_organizacion" al primer usuario de una organización
   tras el primer escaneo de CUALQUIER repo suyo -- pensado solo como
   "déjale ver/gestionar el repo que su propia org acaba de conectar".
   Corregido cambiando el rol auto-concedido a "mantenedor" (acotado de
   verdad por `(user_login, repo)` real vía `get_role`).

2. Además, `user_is_org_admin()` en sí trataba tener "admin_organizacion"
   en UNA SOLA fila de `repo_roles` (tabla sin columna `org_id`) como
   admin GLOBAL sobre TODOS los repos de TODAS las organizaciones --
   ninguna comprobación de organización en absoluto. Confirmado en vivo
   contra un dashboard-backend real: el primer escaneo de una org nueva
   cualquiera se autoconcedía superadmin cross-tenant sobre los datos de
   otros clientes. Corregido añadiendo `repo_roles.org_id` (migración
   `e4f5a6b7c8d9`) y exigiendo que `user_is_org_admin(session, login,
   org_id)` reciba y compare esa columna -- `admin_organizacion` es ahora
   un rol acotado a UNA organización, nunca global (ver
   `org_scope.py::is_site_superadmin` para lo que sí es de instancia
   completa).

Este fichero fija ambas garantías como tests explícitos, no solo los
fixes en tasks.py/db.py -- para que una regresión futura (alguien
reintroduciendo "admin_organizacion" en el auto-grant, o quitando el
filtro por `org_id` de `user_is_org_admin`) falle aquí."""

from __future__ import annotations

from pathlib import Path

from watchgate.dashboard.backend import db as database


def test_mantenedor_role_on_own_repo_does_not_grant_org_admin(tmp_path: Path) -> None:
    """La forma correcta de "dale acceso a tu propio repo recién
    conectado" (lo que tasks.py hace ahora) -- no debe convertir a nadie
    en admin de su organización, y mucho menos de otra."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_role(
            conn, "org-a-user", "orga/their-own-repo", "mantenedor", org_id="org-a"
        )

    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.user_is_org_admin(conn, "org-a-user", "org-a") is False
        assert database.get_role(conn, "org-a-user", "orga/their-own-repo") == "mantenedor"
        # El punto central del hallazgo original: sin rol en el repo de
        # OTRA organización, y sin ser admin de ninguna, no hay forma de
        # leerlo.
        assert database.get_role(conn, "org-a-user", "orgb/victim-repo") is None


def test_admin_organizacion_is_scoped_to_its_own_organization(tmp_path: Path) -> None:
    """`admin_organizacion` concedido sobre un repo de la organización A
    da admin sobre A -- pero NUNCA sobre una organización B distinta,
    aunque el login sea el mismo. Esto es justo lo contrario del fallo
    original (donde una sola fila con este rol, en cualquier repo, daba
    admin GLOBAL): ahora `org_id` es obligatorio y se compara de verdad."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_role(
            conn, "org-a-admin", "orga/some-repo", "admin_organizacion", org_id="org-a"
        )

    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.user_is_org_admin(conn, "org-a-admin", "org-a") is True
        assert database.user_is_org_admin(conn, "org-a-admin", "org-b") is False
        # Sin `org_id` resuelto para lo que se está comprobando, fail-closed.
        assert database.user_is_org_admin(conn, "org-a-admin", None) is False


def test_run_scan_role_grant_never_uses_admin_organizacion() -> None:
    """Red de seguridad a nivel de fuente: el auto-grant de tasks.py tras
    un escaneo nunca debe volver a usar "admin_organizacion" -- si alguien
    lo reintroduce (aunque sea copiando/pegando una línea antigua), este
    test falla inmediato en vez de depender solo de descubrirlo en
    auditoría."""
    import inspect

    from watchgate.dashboard.backend import tasks

    for func in (tasks.run_managed_scan, tasks.run_main_branch_scan, tasks.run_audit_scan):
        source = inspect.getsource(func)
        assert 'upsert_role(dash_conn, user_obj.name, repo_path, "admin_organizacion")' not in (
            source
        ), f"{func.__name__} concede admin_organizacion global tras un escaneo -- ver auditoría"
