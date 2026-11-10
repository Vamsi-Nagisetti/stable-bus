
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    Numeric,
    Date,
    DateTime,
    Index,
    JSON,
    text,
)
from sqlalchemy import Text
from sqlalchemy.orm import relationship, Mapped, mapped_column

from core.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    __table_args__ = (
        Index("ix_bookings_user_id", "user_id"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_journey_date", "journey_date"),
        Index(
            "uq_bookings_user_id_idempotency_key",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_bookings_guest_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
    )

    passengers = relationship(
        "BookingPassenger",
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    temp_booking_ref: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    supplier_refno = Column(String(100), nullable=True)
    transport_pnr = Column(String(100), nullable=True)

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    guest_access_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    customer_mobile: Mapped[str | None] = mapped_column(
        String(15),
        nullable=True,
    )

    passenger_email: Mapped[str | None] = mapped_column(
        String(254),
        nullable=True,
    )

    operator_booking_ref: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

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

    bus_id: Mapped[str] = mapped_column(Text, nullable=False)

    seat_numbers: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )

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
