
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


class Refund(Base):

    __tablename__ = "refunds"

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_refund_idempotency_key",
        ),
        Index("ix_refunds_payment_id", "payment_id"),
        Index("ix_refunds_status", "status"),
        Index("ix_refunds_gateway_refund_id", "gateway_refund_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    payment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("payments.id"),
        nullable=False,
    )

    gateway_refund_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING",
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

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
