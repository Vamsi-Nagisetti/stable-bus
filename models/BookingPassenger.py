
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

from sqlalchemy import (
    Column,
    String,
    Integer,
    Date,
    DateTime,
    ForeignKey,
    Index,
)

from core.database import Base


class BookingPassenger(Base):
    __tablename__ = "booking_passengers"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    booking = relationship(
    "Booking",
    back_populates="passengers",
    )

    booking_id = Column(
        String(36),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    saved_passenger_id = Column(String(36), nullable=True)

    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(20), nullable=False)

    seat_number = Column(String(30), nullable=False)
    ticket_number = Column(String(100), nullable=True)
    # Optional provider/customer details
    title = Column(String(20), nullable=True)
    dob = Column(Date, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_booking_passengers_booking_id", "booking_id"),
    )
