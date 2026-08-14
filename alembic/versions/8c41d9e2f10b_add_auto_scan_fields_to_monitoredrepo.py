"""Add auto_scan fields to MonitoredRepo

Revision ID: 8c41d9e2f10b
Revises: 532ab023f597
Create Date: 2026-08-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8c41d9e2f10b'
down_revision: Union[str, Sequence[str], None] = '532ab023f597'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('monitored_repos', sa.Column('auto_scan_prs', sa.Boolean(), nullable=False, server_default=sa.text('1')))
    op.add_column('monitored_repos', sa.Column('scan_interval_minutes', sa.Integer(), nullable=False, server_default=sa.text('30')))
    op.add_column('monitored_repos', sa.Column('prs_etag', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('monitored_repos', sa.Column('last_polled_at', sa.DateTime(), nullable=True))
    op.add_column('monitored_repos', sa.Column('consecutive_errors', sa.Integer(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('monitored_repos', 'consecutive_errors')
    op.drop_column('monitored_repos', 'last_polled_at')
    op.drop_column('monitored_repos', 'prs_etag')
    op.drop_column('monitored_repos', 'scan_interval_minutes')
    op.drop_column('monitored_repos', 'auto_scan_prs')
