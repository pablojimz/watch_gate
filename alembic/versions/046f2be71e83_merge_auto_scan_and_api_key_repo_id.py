"""merge_auto_scan_and_api_key_repo_id

Revision ID: 046f2be71e83
Revises: 8c41d9e2f10b, 9adca6739548
Create Date: 2026-08-14 09:45:52.009215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '046f2be71e83'
down_revision: Union[str, Sequence[str], None] = ('8c41d9e2f10b', '9adca6739548')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
