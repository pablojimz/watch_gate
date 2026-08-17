"""add RepoTokenUsage (consumo de tokens por repo, modo CLI/engine local)

Revision ID: b7e91c2a4d3f
Revises: 046f2be71e83
Create Date: 2026-08-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e91c2a4d3f"
down_revision: str | Sequence[str] | None = "046f2be71e83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "repo_token_usage",
        sa.Column("repo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("month", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("repo", "month"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("repo_token_usage")
