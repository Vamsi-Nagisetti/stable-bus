
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    UniqueConstraint,
    Index,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Payment(Base):
    __tablename__ = "payments"

    __table_args__ = (
        UniqueConstraint("payment_attempt_id", name="uq_payment_attempt_id"),
        UniqueConstraint("idempotency_key", name="uq_payment_idempotency_key"),
        Index("ix_payments_booking_id", "booking_id"),
        Index("ix_payments_gateway_order_id", "gateway_order_id"),
        Index("ix_payments_status", "status"),
        Index(
            "ix_payments_reconciliation_due",
            "status",
            "next_reconciliation_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payment_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    gateway: Mapped[str] = mapped_column(String(30), nullable=False)
    gateway_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", nullable=False
    )

    # CREATED / PROCESSING / PENDING / UNKNOWN / SUCCESS / FAILED / MANUAL_REVIEW
    status: Mapped[str] = mapped_column(
        String(30), default="CREATED", nullable=False
    )

    idempotency_key: Mapped[str] = mapped_column(String(150), nullable=False)

    # Reconciliation scheduling and worker coordination
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
