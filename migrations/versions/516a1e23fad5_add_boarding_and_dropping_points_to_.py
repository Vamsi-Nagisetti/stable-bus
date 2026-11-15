"""add boarding and dropping points to bookings

Revision ID: 516a1e23fad5
Revises: 1f847bd7d3c8
Create Date: 2026-11-15 08:15:35.847149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '516a1e23fad5'
down_revision: Union[str, Sequence[str], None] = '1f847bd7d3c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("boarding_point", sa.JSON(), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("dropping_point", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "dropping_point")
    op.drop_column("bookings", "boarding_point")
