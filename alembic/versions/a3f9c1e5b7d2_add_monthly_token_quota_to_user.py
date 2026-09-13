"""add monthly_token_quota to user

Revision ID: a3f9c1e5b7d2
Revises: f3a7c9b2e1d4
Create Date: 2026-09-08 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c1e5b7d2'
down_revision: Union[str, Sequence[str], None] = 'f3a7c9b2e1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default numérico (no el símbolo de Python) para que las filas
    # YA existentes también queden con la cuota "casi ilimitada" -- ver
    # DEFAULT_USER_MONTHLY_TOKEN_QUOTA en watchgate/db/models.py.
    op.add_column(
        'users',
        sa.Column(
            'monthly_token_quota',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('2000000000'),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'monthly_token_quota')
