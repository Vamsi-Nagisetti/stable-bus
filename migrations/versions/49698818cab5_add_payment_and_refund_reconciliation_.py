
"""add payment and refund reconciliation fields

Revision ID: 49698818cab5
Revises: d988f90d37da
Create Date: 2026-11-14 14:17:37.450134
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "49698818cab5"
down_revision: Union[str, Sequence[str], None] = "d988f90d37da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Payments: add reconciliation fields with temporary DB defaults
    # so existing records can be migrated safely.

    op.add_column(
        "payments",
        sa.Column(
            "reconciliation_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "next_reconciliation_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "reconciliation_deadline_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '24 hours'"),
        ),
    )
    op.add_column(
        "payments",
        sa.Column("reconciliation_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("last_reconciliation_error", sa.String(length=2000), nullable=True),
    )

    op.create_index(
        "ix_payments_reconciliation_due",
        "payments",
        ["status", "next_reconciliation_at"],
        unique=False,
    )

    # Refunds
    op.add_column(
        "refunds",
        sa.Column(
            "reconciliation_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "refunds",
        sa.Column(
            "next_reconciliation_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "refunds",
        sa.Column(
            "reconciliation_deadline_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '24 hours'"),
        ),
    )
    op.add_column(
        "refunds",
        sa.Column("reconciliation_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refunds",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refunds",
        sa.Column("last_reconciliation_error", sa.String(length=2000), nullable=True),
    )

    op.create_index(
        "ix_refunds_reconciliation_due",
        "refunds",
        ["status", "next_reconciliation_at"],
        unique=False,
    )

    # Remove temporary defaults; application code manages new records.
    for table in ("payments", "refunds"):
        for column in (
            "reconciliation_attempts",
            "next_reconciliation_at",
            "reconciliation_deadline_at",
        ):
            op.alter_column(
                table,
                column,
                existing_type=(
                    sa.Integer()
                    if column == "reconciliation_attempts"
                    else sa.DateTime(timezone=True)
                ),
                server_default=None,
            )


def downgrade() -> None:
    op.drop_index("ix_refunds_reconciliation_due", table_name="refunds")
    op.drop_column("refunds", "last_reconciliation_error")
    op.drop_column("refunds", "last_reconciled_at")
    op.drop_column("refunds", "reconciliation_locked_until")
    op.drop_column("refunds", "reconciliation_deadline_at")
    op.drop_column("refunds", "next_reconciliation_at")
    op.drop_column("refunds", "reconciliation_attempts")

    op.drop_index("ix_payments_reconciliation_due", table_name="payments")
    op.drop_column("payments", "last_reconciliation_error")
    op.drop_column("payments", "last_reconciled_at")
    op.drop_column("payments", "reconciliation_locked_until")
    op.drop_column("payments", "reconciliation_deadline_at")
    op.drop_column("payments", "next_reconciliation_at")
    op.drop_column("payments", "reconciliation_attempts")
