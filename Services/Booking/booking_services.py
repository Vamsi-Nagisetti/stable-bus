import logging

from core.constants.booking_status import BookingStatus

logger = logging.getLogger("stablebus.booking")


class InvalidBookingTransition(Exception):
    pass


class BookingStatusService:

    ALLOWED_TRANSITIONS = {
        BookingStatus.INITIATED: {
            BookingStatus.TEMP_BOOKING_PENDING,
            BookingStatus.BOOKING_FAILED,
        },
        BookingStatus.TEMP_BOOKING_PENDING: {
            BookingStatus.TEMP_BOOKED,
            BookingStatus.BOOKING_FAILED,
        },
        BookingStatus.TEMP_BOOKED: {
            BookingStatus.PAYMENT_PENDING,
            BookingStatus.BOOKING_FAILED,
        },
        BookingStatus.PAYMENT_PENDING: {
            BookingStatus.PAYMENT_VERIFIED,
            BookingStatus.BOOKING_FAILED,
        },
        BookingStatus.PAYMENT_VERIFIED: {
            BookingStatus.TICKETING_PENDING,
            BookingStatus.BOOKING_FAILED,
        },
        BookingStatus.TICKETING_PENDING: {
            BookingStatus.CONFIRMED,
            BookingStatus.TICKETING_UNKNOWN,
            BookingStatus.BOOKING_FAILED,
        },
        BookingStatus.TICKETING_UNKNOWN: {
            BookingStatus.CONFIRMED,
            BookingStatus.BOOKING_FAILED,
        },
        BookingStatus.CONFIRMED: {
            BookingStatus.CANCELLATION_PENDING,
        },
        BookingStatus.CANCELLATION_PENDING: {
            BookingStatus.CANCELLED,
            BookingStatus.CONFIRMED,
        },
        BookingStatus.BOOKING_FAILED: set(),
        BookingStatus.CANCELLED: set(),
    }

    @classmethod
    def validate_transition(cls, current_status: str, new_status: str):
        allowed = cls.ALLOWED_TRANSITIONS.get(current_status, set())

        if new_status not in allowed:
            raise InvalidBookingTransition(
                f"Invalid booking transition: "
                f"{current_status} -> {new_status}"
            )

    @classmethod
    def transition(cls, booking, new_status: str):
        cls.validate_transition(booking.status, new_status)

        logger.info(
            "Booking status transition: %s -> %s",
            booking.status,
            new_status,
        )

        booking.status = new_status

        return booking
