"""add_github_user_and_org_credentials: añade campos de GitHub API y token a dashboard_users y llm_settings, y ui_settings_json a dashboard_users.

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dashboard_users", sa.Column("github_api_url", sa.String(), nullable=True))
    op.add_column("dashboard_users", sa.Column("github_token", sa.String(), nullable=True))
    op.add_column("dashboard_users", sa.Column("ui_settings_json", sa.String(), nullable=True))

    op.add_column("llm_settings", sa.Column("github_api_url", sa.String(), nullable=True))
    op.add_column("llm_settings", sa.Column("github_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("dashboard_users", "ui_settings_json")
    op.drop_column("dashboard_users", "github_token")
    op.drop_column("dashboard_users", "github_api_url")

    op.drop_column("llm_settings", "github_token")
    op.drop_column("llm_settings", "github_api_url")
