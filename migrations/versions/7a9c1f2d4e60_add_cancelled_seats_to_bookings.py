"""add cancelled seats to bookings

Revision ID: 7a9c1f2d4e60
Revises: 516a1e23fad5
Create Date: 2026-11-17
"""
from alembic import op
import sqlalchemy as sa

revision = "7a9c1f2d4e60"
down_revision = "516a1e23fad5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bookings",
        sa.Column("cancelled_seat_numbers", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.alter_column("bookings", "cancelled_seat_numbers", server_default=None)


def downgrade():
    op.drop_column("bookings", "cancelled_seat_numbers")
