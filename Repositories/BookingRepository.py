
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

    def get_by_user_id(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Booking]:

        stmt = (
            select(Booking)
            .where(Booking.user_id == user_id)
            .order_by(
                Booking.created_at.desc(),
                Booking.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(self.database.scalars(stmt).all())

    def update_status(
        self,
        booking_id: str,
        status: str,
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

    def get_by_idempotency_key(
        self,
        user_id: str | None,
        idempotency_key: str,
    ) -> Booking | None:

        stmt = select(Booking).where(
            Booking.idempotency_key == idempotency_key
        )

        if user_id is None:
            stmt = stmt.where(Booking.user_id.is_(None))
        else:
            stmt = stmt.where(Booking.user_id == user_id)

        return self.database.scalar(stmt)
