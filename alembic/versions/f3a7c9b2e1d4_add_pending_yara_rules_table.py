"""add pending yara rules table

Revision ID: f3a7c9b2e1d4
Revises: b8ec3d2fcd13
Create Date: 2026-08-31 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f3a7c9b2e1d4'
down_revision: Union[str, Sequence[str], None] = 'b8ec3d2fcd13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pending_yara_rules',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('org_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('repo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('pr_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('rule_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('yara_source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('reviewed_by', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_pending_yara_rules_org_id'), 'pending_yara_rules', ['org_id'], unique=False
    )
    op.create_index(
        op.f('ix_pending_yara_rules_rule_name'), 'pending_yara_rules', ['rule_name'], unique=False
    )
    op.create_index(
        op.f('ix_pending_yara_rules_status'), 'pending_yara_rules', ['status'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pending_yara_rules_status'), table_name='pending_yara_rules')
    op.drop_index(op.f('ix_pending_yara_rules_rule_name'), table_name='pending_yara_rules')
    op.drop_index(op.f('ix_pending_yara_rules_org_id'), table_name='pending_yara_rules')
    op.drop_table('pending_yara_rules')
