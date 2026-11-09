
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    String,
    Numeric,
    Date,
    DateTime,
    Index,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Booking(Base):

    __tablename__ = "bookings"

    __table_args__ = (
        Index("ix_bookings_user_id", "user_id"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_journey_date", "journey_date"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    # AO Pay references
    operator_booking_ref: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Journey details
    source_city_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    destination_city_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    journey_date: Mapped[datetime.date] = mapped_column(
        Date,
        nullable=False,
    )

    bus_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    seat_numbers: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )

    # Payment amount
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )

    # Booking lifecycle
    status: Mapped[str] = mapped_column(
        String(40),
        default="INITIATED",
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
