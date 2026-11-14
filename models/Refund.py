
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Refund(Base):
    __tablename__ = "refunds"

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_refund_idempotency_key"),
        Index("ix_refunds_payment_id", "payment_id"),
        Index("ix_refunds_status", "status"),
        Index("ix_refunds_gateway_refund_id", "gateway_refund_id"),
        Index(
            "ix_refunds_reconciliation_due",
            "status",
            "next_reconciliation_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    payment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payments.id"), nullable=False
    )
    gateway_refund_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING", nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(150), nullable=False)

    reconciliation_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    next_reconciliation_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    reconciliation_deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: _utc_now() + timedelta(hours=24),
        nullable=False,
    )
    reconciliation_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reconciliation_error: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
