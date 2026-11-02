
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.Booking import Booking


class BookingRepository:

    def __init__(self, database: Session):
        self.database = database

    def save(self, booking: Booking) -> Booking:
        self.database.add(booking)
        self.database.flush()
        return booking

    def get_by_id(self, booking_id: str) -> Booking | None:
        stmt = select(Booking).where(
            Booking.id == booking_id
        )
        return self.database.scalar(stmt)

    def get_by_user_id(self, user_id: str) -> list[Booking]:
        stmt = select(Booking).where(
            Booking.user_id == user_id
        )
        return list(self.database.scalars(stmt).all())

    def update_status(
        self,
        booking_id: str,
        status: str
    ) -> Booking | None:

        booking = self.get_by_id(booking_id)

        if booking is None:
            return None

        booking.status = status
        self.database.flush()

        return booking

    def delete_by_id(self, booking_id: str) -> bool:
        booking = self.get_by_id(booking_id)

        if booking is None:
            return False

        self.database.delete(booking)
        self.database.flush()

        return True
