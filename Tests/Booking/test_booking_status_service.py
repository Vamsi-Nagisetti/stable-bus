import pytest
from types import SimpleNamespace

from Services.Booking.booking_services import (
    BookingStatusService,
    InvalidBookingTransition,
)
from core.constants.booking_status import BookingStatus


@pytest.mark.parametrize(
    "current,new",
    [
        (BookingStatus.INITIATED, BookingStatus.TEMP_BOOKING_PENDING),
        (BookingStatus.TEMP_BOOKING_PENDING, BookingStatus.TEMP_BOOKED),
        (BookingStatus.TEMP_BOOKED, BookingStatus.PAYMENT_PENDING),
        (BookingStatus.PAYMENT_PENDING, BookingStatus.PAYMENT_VERIFIED),
        (BookingStatus.PAYMENT_VERIFIED, BookingStatus.TICKETING_PENDING),
        (BookingStatus.TICKETING_PENDING, BookingStatus.CONFIRMED),
        (BookingStatus.TICKETING_PENDING, BookingStatus.TICKETING_UNKNOWN),
        (BookingStatus.TICKETING_UNKNOWN, BookingStatus.CONFIRMED),
        (BookingStatus.TICKETING_UNKNOWN, BookingStatus.BOOKING_FAILED),
        (BookingStatus.CONFIRMED, BookingStatus.CANCELLATION_PENDING),
        (BookingStatus.CANCELLATION_PENDING, BookingStatus.CANCELLED),
        (BookingStatus.CANCELLATION_PENDING, BookingStatus.CONFIRMED),
    ],
)
def test_valid_booking_transitions(current, new):
    booking = SimpleNamespace(status=current)

    result = BookingStatusService.transition(booking, new)

    assert result.status == new


@pytest.mark.parametrize(
    "current,new",
    [
        (BookingStatus.INITIATED, BookingStatus.CONFIRMED),
        (BookingStatus.TEMP_BOOKED, BookingStatus.CONFIRMED),
        (BookingStatus.PAYMENT_PENDING, BookingStatus.CONFIRMED),
        (BookingStatus.CONFIRMED, BookingStatus.BOOKING_FAILED),
        (BookingStatus.CANCELLED, BookingStatus.CONFIRMED),
        (BookingStatus.BOOKING_FAILED, BookingStatus.TEMP_BOOKED),
    ],
)
def test_invalid_booking_transitions(current, new):
    booking = SimpleNamespace(status=current)

    with pytest.raises(InvalidBookingTransition):
        BookingStatusService.transition(booking, new)


def test_invalid_transition_does_not_change_status():
    booking = SimpleNamespace(status=BookingStatus.INITIATED)

    with pytest.raises(InvalidBookingTransition):
        BookingStatusService.transition(
            booking,
            BookingStatus.CONFIRMED,
        )

    assert booking.status == BookingStatus.INITIATED