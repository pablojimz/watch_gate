"""drop_admin_organizacion_role: quita "admin_organizacion" del RBAC.

Se quitó el rol "admin_organizacion" del RBAC -- ya no hay ningún rol
capaz de administrar una organización entera, solo "mantenedor" (acotado
a un repo concreto) y "revisor". Antes de endurecer el CheckConstraint,
cualquier fila existente con ese rol se reconcede como "mantenedor" (en
vez de borrarla) para no dejar a nadie sin acceso a un repo que ya
gestionaba -- ver watchgate/dashboard/backend/db.py::user_is_org_admin
(se conserva devolviendo siempre `False`, con muchos llamadores fuera del
propio Dashboard que ya degradan correctamente al comprobar el rol normal
por repo) y watchgate/dashboard/backend/models.py::RepoRole.

Nombre real del constraint en Postgres (Auditoría, hallazgo real durante
esta misma migración): la base de datos de este despliegue tiene la
tabla `repo_roles` con su CHECK nombrado por Postgres como
`repo_roles_role_check` (nombre por defecto de columna) en vez de
`ck_repo_roles_role` (el nombre explícito que declaraba el modelo desde
el baseline `a1b2c3d4e5f6`) -- de cuándo/cómo se creó esa tabla en
concreto antes de que este historial de Alembic la rastreara. `DROP
CONSTRAINT IF EXISTS` con los dos nombres cubre ambos casos sin fallar;
la constraint queda re-creada siempre con el nombre explícito del modelo,
para que a partir de aquí no vuelva a haber ambigüedad. SQLite no soporta
`ALTER TABLE ... DROP CONSTRAINT` -- ahí hace falta `batch_alter_table`
(recrea la tabla entera por debajo), que además ya conoce el nombre
correcto porque SQLite sí lo declara tal cual el modelo pide.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-01 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: str | Sequence[str] | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REPO_ROLES = sa.table(
    "repo_roles",
    sa.column("role", sa.String()),
)


def upgrade() -> None:
    # Reconceder antes de endurecer el constraint -- si esto corriera al
    # revés (constraint primero), la propia UPDATE fallaría contra las
    # filas que todavía dicen "admin_organizacion".
    op.execute(
        _REPO_ROLES.update()
        .where(_REPO_ROLES.c.role == "admin_organizacion")
        .values(role="mantenedor")
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # `IF EXISTS` con los dos nombres posibles -- ver docstring del
        # módulo sobre por qué esta base concreta tiene el auto-generado
        # (`repo_roles_role_check`) en vez del explícito del modelo.
        op.execute("ALTER TABLE repo_roles DROP CONSTRAINT IF EXISTS ck_repo_roles_role")
        op.execute("ALTER TABLE repo_roles DROP CONSTRAINT IF EXISTS repo_roles_role_check")
        op.execute(
            "ALTER TABLE repo_roles ADD CONSTRAINT ck_repo_roles_role "
            "CHECK (role IN ('mantenedor','revisor'))"
        )
    else:
        with op.batch_alter_table("repo_roles") as batch_op:
            batch_op.drop_constraint("ck_repo_roles_role", type_="check")
            batch_op.create_check_constraint(
                "ck_repo_roles_role",
                "role IN ('mantenedor','revisor')",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE repo_roles DROP CONSTRAINT IF EXISTS ck_repo_roles_role")
        op.execute(
            "ALTER TABLE repo_roles ADD CONSTRAINT ck_repo_roles_role "
            "CHECK (role IN ('admin_organizacion','mantenedor','revisor'))"
        )
    else:
        with op.batch_alter_table("repo_roles") as batch_op:
            batch_op.drop_constraint("ck_repo_roles_role", type_="check")
            batch_op.create_check_constraint(
                "ck_repo_roles_role",
                "role IN ('admin_organizacion','mantenedor','revisor')",
            )
    # No se puede recuperar qué filas ERAN "admin_organizacion" antes del
    # upgrade -- quedan como "mantenedor", que es el rol correcto y más
    # amplio disponible después de bajar esta migración.
