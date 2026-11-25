"""added preregisted users table

Revision ID: fa06f2b59412
Revises: 9f3c2a7b1d40
Create Date: 2026-11-17 16:34:35.214762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa06f2b59412'
down_revision: Union[str, Sequence[str], None] = '9f3c2a7b1d40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
