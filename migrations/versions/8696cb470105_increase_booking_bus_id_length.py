from alembic import op
import sqlalchemy as sa


revision = "8696cb470105"
down_revision = "cdd2451344b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "bookings",
        "bus_id",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "bookings",
        "bus_id",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=False,
    )