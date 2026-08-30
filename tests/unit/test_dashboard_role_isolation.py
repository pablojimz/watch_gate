"""Tests de aislamiento de roles del Dashboard (watchgate/dashboard/backend/db.py).

Auditoría (hallazgo crítico, corregido): `tasks.py` (run_managed_scan/
run_main_branch_scan/run_audit_scan) concedía "admin_organizacion" al
primer usuario de una organización tras el primer escaneo de CUALQUIER
repo suyo -- pensado solo como "déjale ver/gestionar el repo que su
propia org acaba de conectar". Pero `user_is_org_admin()` trata tener ese
rol en UNA SOLA fila de `repo_roles` (tabla sin columna org_id) como
admin GLOBAL sobre TODOS los repos de TODAS las organizaciones -- ninguna
comprobación de organización en absoluto. Confirmado en vivo contra un
dashboard-backend real: el primer escaneo de una org nueva cualquiera se
autoconcedía superadmin cross-tenant sobre los datos de otros clientes
(listar/leer/escribir roles ajenos, ver scores de repos ajenos, e incluso
mergear PRs ajenos vía `feedback.py::accept_score` -> `_resolve_merge_client`,
que solo mira `repo_path`, sin comprobación de organización tampoco).

Corregido cambiando el rol auto-concedido a "mantenedor" (sí acotado por
`(user_login, repo)` real vía `get_role`). Este fichero fija esa garantía
de seguridad como test explícito, no solo el fix en tasks.py -- para que
una regresión futura (alguien reintroduciendo "admin_organizacion" ahí,
o cualquier otro camino que conceda ese rol sin querer) falle aquí."""

from __future__ import annotations

from pathlib import Path

from watchgate.dashboard.backend import db as database


def test_mantenedor_role_on_own_repo_does_not_grant_global_admin(tmp_path: Path) -> None:
    """La forma correcta de "dale acceso a tu propio repo recién
    conectado" (lo que tasks.py hace ahora) -- no debe convertir a nadie
    en admin de la plataforma."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_role(conn, "org-a-user", "orga/their-own-repo", "mantenedor")

    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.user_is_org_admin(conn, "org-a-user") is False
        assert database.get_role(conn, "org-a-user", "orga/their-own-repo") == "mantenedor"
        # El punto central del hallazgo: sin rol en el repo de OTRA
        # organización, y sin ser admin global, no hay forma de leerlo.
        assert database.get_role(conn, "org-a-user", "orgb/victim-repo") is None


def test_admin_organizacion_on_a_single_repo_is_still_global_by_design_flaw(
    tmp_path: Path,
) -> None:
    """Documenta el comportamiento REAL de `user_is_org_admin` (no acota
    por organización -- limitación arquitectónica conocida, ver auditoría)
    para que quede explícito y visible: "admin_organizacion" sigue siendo
    un rol de alcance GLOBAL, nunca debe concederse automáticamente ni sin
    verificación humana explícita de que quien lo recibe debe tener poder
    sobre TODA la plataforma, no solo su propia organización."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.upsert_role(conn, "real-admin", "orga/some-repo", "admin_organizacion")

    with database.db_session(tmp_path / "dashboard.db") as conn:
        assert database.user_is_org_admin(conn, "real-admin") is True


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
