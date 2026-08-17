"""drop auto_scan_prs/scan_interval_minutes de MonitoredRepo (repolling periódico eliminado)

Revision ID: c4f8a1d9e2b6
Revises: b7e91c2a4d3f
Create Date: 2026-08-17 00:00:00.000000

El repolling periódico automático (scheduler + auto_scan_prs +
scan_interval_minutes) se elimina a petición explícita: todo escaneo de un
repo ya conectado requiere pulsar "Escanear" en el Dashboard -- ver
watchgate/service/repo_polling.py y watchgate/dashboard/backend/routers/repos.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f8a1d9e2b6"
down_revision: str | Sequence[str] | None = "b7e91c2a4d3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("monitored_repos", "auto_scan_prs")
    op.drop_column("monitored_repos", "scan_interval_minutes")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "monitored_repos",
        sa.Column("scan_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "monitored_repos",
        sa.Column("auto_scan_prs", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
