"""add blocked authors table

Revision ID: b8ec3d2fcd13
Revises: 2012802e66bc
Create Date: 2026-08-26 13:09:17.021318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b8ec3d2fcd13'
down_revision: Union[str, Sequence[str], None] = '2012802e66bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'blocked_authors',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('org_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('author_login', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('blocked_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('blocked_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_blocked_authors_org_id'), 'blocked_authors', ['org_id'], unique=False)
    op.create_index(op.f('ix_blocked_authors_author_login'), 'blocked_authors', ['author_login'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_blocked_authors_author_login'), table_name='blocked_authors')
    op.drop_index(op.f('ix_blocked_authors_org_id'), table_name='blocked_authors')
    op.drop_table('blocked_authors')
