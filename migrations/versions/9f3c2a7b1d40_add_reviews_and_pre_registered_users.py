"""add reviews and pre-registered users

Revision ID: 9f3c2a7b1d40
Revises: 7a9c1f2d4e60
Create Date: 2026-11-17
"""
from alembic import op
import sqlalchemy as sa

revision = "9f3c2a7b1d40"
down_revision = "7a9c1f2d4e60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("booking_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("bus_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_reviews_booking_id"),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_1_to_5"),
    )
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"], unique=False)
    op.create_index("ix_reviews_bus_id_created_at", "reviews", ["bus_id", "created_at"], unique=False)

    op.create_table(
        "pre_registered_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("mobile", sa.String(length=10), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mobile", name="uq_pre_registered_users_mobile"),
        sa.UniqueConstraint("email", name="uq_pre_registered_users_email"),
    )


def downgrade() -> None:
    op.drop_table("pre_registered_users")
    op.drop_index("ix_reviews_bus_id_created_at", table_name="reviews")
    op.drop_index("ix_reviews_user_id", table_name="reviews")
    op.drop_table("reviews")
