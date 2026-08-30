"""org_scope.py — resolución de organización real (Engine DB) para el
control de acceso del Dashboard.

Auditoría (hallazgo crítico, corregido): `repo_roles` (Dashboard DB) no
tenía ninguna columna de organización -- tener `admin_organizacion` en UNA
fila se trataba como admin GLOBAL sobre TODOS los repos de TODAS las
organizaciones. El fix añade `RepoRole.org_id` (ver models.py), pero para
usarlo hace falta saber, en cada petición, "¿de qué organización es esto?"
-- ese dato vive en la Engine DB (`watchgate.db.models.Organization`/
`MonitoredRepo`, una base física distinta de la del Dashboard, ver el
docstring de `dashboard/backend/models.py`). Este módulo centraliza esa
resolución para no repetirla ad hoc en cada router.

Además de "por-organización", se introduce un segundo nivel, genuinamente
de instancia completa (`is_site_superadmin`): LLM settings, branding y
gestión de cuentas locales no son datos de UNA organización -- son
configuración compartida de todo el despliegue (filas singleton / tabla
`dashboard_users` sin columna de organización). Confundir ambos niveles
fue precisamente el bug original: "admin_organizacion" hacía de las dos
cosas a la vez, sin que nada lo distinguiera.
"""

from __future__ import annotations

import os

from sqlmodel import Session, select

from watchgate.db.models import MonitoredRepo


def resolve_caller_org_id(engine_session: Session, user_login: str) -> str:
    """Organización real del usuario autenticado -- crea su `User`/
    `Organization` propios si es la primera vez que se resuelve (mismo
    patrón ya establecido en `routers/keys.py::_get_or_create_db_user`,
    reusado aquí en vez de duplicado)."""
    from watchgate.dashboard.backend.routers.keys import _get_or_create_db_user

    db_user = _get_or_create_db_user(engine_session, user_login)
    # `User.org_id` está tipado `str | None` a nivel de esquema (columna
    # nullable), pero `_get_or_create_db_user` garantiza una Organización
    # real por diseño (ver su propio docstring) -- nunca None en la
    # práctica para un usuario que acaba de crear/recuperar esa función.
    assert db_user.org_id is not None
    return db_user.org_id


def resolve_org_id_for_repo(engine_session: Session, repo: str) -> str | None:
    """Organización dueña de `repo`, si tiene un `MonitoredRepo` real --
    `None` si el repo solo existe vía ingesta genérica (`POST /scores`
    desde CI, sin conectar) o no existe en absoluto. `None` debe tratarse
    como "no se puede verificar la organización", nunca como "vale
    cualquier admin" -- ver `db.py::user_is_org_admin`, que ya trata
    `org_id=None` como fail-closed."""
    repo_row = engine_session.exec(
        select(MonitoredRepo).where(MonitoredRepo.repo_path == repo)
    ).first()
    return repo_row.org_id if repo_row is not None else None


def resolve_org_repo_paths(engine_session: Session, org_id: str) -> set[str]:
    """Todos los `MonitoredRepo.repo_path` reales de una organización --
    usado para que un admin de esa organización vea en `/repos` los repos
    que ya conectó aunque todavía no tengan ningún `RepoRole` asignado a
    nadie (p. ej. recién conectado, antes del primer escaneo)."""
    rows = engine_session.exec(
        select(MonitoredRepo.repo_path).where(MonitoredRepo.org_id == org_id)
    ).all()
    return set(rows)


def is_site_superadmin(user_login: str) -> bool:
    """Segundo nivel, genuinamente de instancia completa -- ver docstring
    del módulo. Deliberadamente NO es una fila de base de datos ni algo
    auto-concedible por ningún flujo de escaneo/análisis (que es
    exactamente cómo se coló el bug original): solo quien controla las
    variables de entorno de ESTE despliegue decide quién tiene este nivel,
    igual que ya decide `WATCHGATE_DASHBOARD_SECRET`/dev mode/CORS. Vacío
    por defecto salvo `"admin"` (el login que `seed_demo()` siembra como
    demo/desarrollo) para que un checkout local siga funcionando sin
    configuración adicional; un despliegue real debe fijar esta variable
    explícitamente."""
    raw = os.environ.get("WATCHGATE_DASHBOARD_SITE_ADMIN_LOGINS", "admin")
    logins = {login.strip().lower() for login in raw.split(",") if login.strip()}
    return user_login.strip().lower() in logins
