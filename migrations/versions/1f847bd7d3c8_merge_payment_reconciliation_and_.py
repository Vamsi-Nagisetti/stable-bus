"""merge payment reconciliation and notification migrations

Revision ID: 1f847bd7d3c8
Revises: 49698818cab5, dd96da297513
Create Date: 2026-11-14 15:13:43.813485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f847bd7d3c8'
down_revision: Union[str, Sequence[str], None] = ('49698818cab5', 'dd96da297513')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
