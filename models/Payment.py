
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Payment(Base):

    __tablename__ = "payments"

    __table_args__ = (
        UniqueConstraint(
            "payment_attempt_id",
            name="uq_payment_attempt_id",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_payment_idempotency_key",
        ),
        Index("ix_payments_booking_id", "booking_id"),
        Index("ix_payments_gateway_order_id", "gateway_order_id"),
        Index("ix_payments_status", "status"),
    )

    # Internal payment identifier
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Associated StableBus booking
    booking_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    # Each payment attempt gets a unique identifier
    payment_attempt_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    # Payment gateway: RAZORPAY / CASHFREE
    gateway: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Gateway references
    gateway_order_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    gateway_payment_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Payment details
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )

    # CREATED / PENDING / SUCCESS / FAILED / REFUNDED
    status: Mapped[str] = mapped_column(
        String(30),
        default="CREATED",
        nullable=False,
    )

    # Idempotency
    idempotency_key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
