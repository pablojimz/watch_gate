"""Add monitored_repo_id to UserAPIKey

Revision ID: 9adca6739548
Revises: 532ab023f597
Create Date: 2026-08-13 11:34:07.817839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9adca6739548'
down_revision: Union[str, Sequence[str], None] = '532ab023f597'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Columna NULLABLE a propósito: filas de user_api_keys creadas antes de
    # este cambio ("claves legado") no tienen repo asignado y no se
    # invalidan ni se backfillean aquí -- la obligatoriedad de un repo para
    # claves NUEVAS se impone en la capa de API
    # (dashboard/backend/routers/keys.py::create_key), no en el esquema.
    op.add_column(
        'user_api_keys',
        sa.Column('monitored_repo_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(
        op.f('ix_user_api_keys_monitored_repo_id'),
        'user_api_keys',
        ['monitored_repo_id'],
        unique=False,
    )
    with op.batch_alter_table('user_api_keys') as batch_op:
        batch_op.create_foreign_key(
            'fk_user_api_keys_monitored_repo_id_monitored_repos',
            'monitored_repos',
            ['monitored_repo_id'],
            ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user_api_keys') as batch_op:
        batch_op.drop_constraint(
            'fk_user_api_keys_monitored_repo_id_monitored_repos', type_='foreignkey'
        )
    op.drop_index(op.f('ix_user_api_keys_monitored_repo_id'), table_name='user_api_keys')
    op.drop_column('user_api_keys', 'monitored_repo_id')
