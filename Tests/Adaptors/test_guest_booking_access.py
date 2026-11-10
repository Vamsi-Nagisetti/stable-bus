
import re
from types import SimpleNamespace

from Orchestrators.booking_orchestrator import BookingOrchestrator


def make_booking(user_id=None, token_hash=None):
    return SimpleNamespace(
        id="booking-123",
        user_id=user_id,
        guest_access_token_hash=token_hash,
    )


def test_guest_token_generation():
    token = BookingOrchestrator.generate_guest_token()

    assert isinstance(token, str)
    assert len(token) >= 32


def test_guest_token_hash_is_sha256():
    token = BookingOrchestrator.generate_guest_token()

    token_hash = BookingOrchestrator.hash_guest_token(token)

    assert re.fullmatch(r"[a-f0-9]{64}", token_hash)
    assert token_hash != token


def test_guest_token_hash_is_consistent():
    token = BookingOrchestrator.generate_guest_token()

    assert (
        BookingOrchestrator.hash_guest_token(token)
        == BookingOrchestrator.hash_guest_token(token)
    )


def test_guest_can_access_booking_with_valid_token():
    token = BookingOrchestrator.generate_guest_token()
    booking = make_booking(
        token_hash=BookingOrchestrator.hash_guest_token(token)
    )

    assert BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id=None,
        guest_access_token=token,
    ) is True


def test_guest_cannot_access_booking_with_wrong_token():
    token = BookingOrchestrator.generate_guest_token()
    booking = make_booking(
        token_hash=BookingOrchestrator.hash_guest_token(token)
    )

    assert BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id=None,
        guest_access_token="wrong-token",
    ) is False


def test_guest_cannot_access_booking_without_token():
    booking = make_booking(token_hash="a" * 64)

    assert BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id=None,
        guest_access_token=None,
    ) is False


def test_user_can_access_own_booking():
    booking = make_booking(user_id="user-123")

    assert BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id="user-123",
        guest_access_token=None,
    ) is True


def test_user_cannot_access_another_users_booking():
    booking = make_booking(user_id="user-123")

    assert BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id="user-456",
        guest_access_token=None,
    ) is False


def test_guest_cannot_access_registered_users_booking():
    booking = make_booking(
        user_id="user-123",
        token_hash="a" * 64,
    )

    assert BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id=None,
        guest_access_token="some-token",
    ) is False


def test_missing_booking_is_not_authorized():
    assert BookingOrchestrator.authorize_booking(
        booking=None,
        user_id=None,
        guest_access_token="some-token",
    ) is False
