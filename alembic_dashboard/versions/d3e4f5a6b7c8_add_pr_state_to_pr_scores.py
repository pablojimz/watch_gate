"""add_pr_state_to_pr_scores: añade pr_state ("open"/"closed") a pr_scores, para poder ocultar PRs ya cerradas/mergeadas de los listados de pendientes sin borrar su histórico.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-18 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pr_scores",
        sa.Column("pr_state", sa.String(), nullable=False, server_default="open"),
    )


def downgrade() -> None:
    op.drop_column("pr_scores", "pr_state")
