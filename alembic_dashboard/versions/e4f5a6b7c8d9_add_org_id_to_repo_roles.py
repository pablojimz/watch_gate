"""add_org_id_to_repo_roles: acota repo_roles por organización.

Auditoría (hallazgo crítico, corregido): "admin_organizacion" en UNA fila
de esta tabla se trataba como admin GLOBAL sobre TODOS los repos de TODAS
las organizaciones -- confirmado en vivo, compromiso cross-tenant
completo. `org_id` acota cada fila a la organización real (string plano,
sin FK -- apunta a `Organization.id` de la Engine DB, una base física
distinta). Nullable a propósito: las filas ya existentes se quedan sin
efecto de admin (fail-closed) hasta que se reconceden explícitamente con
`org_id` real, en vez de asumir que un admin_organizacion antiguo sigue
siendo válido sin saber de qué organización viene.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-30 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repo_roles",
        sa.Column("org_id", sa.String(), nullable=True),
    )
    op.create_index("ix_repo_roles_org_id", "repo_roles", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_repo_roles_org_id", table_name="repo_roles")
    op.drop_column("repo_roles", "org_id")
