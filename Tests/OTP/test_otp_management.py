
import json
from unittest.mock import Mock

import pytest

from Adaptors.Cache.CacheBaseAdaptor import CacheBaseAdaptor
from Management.OtpMangement import OTPManagement, OTPDeliveryError


@pytest.fixture
def otp_dependencies(monkeypatch):
    monkeypatch.setenv("OTP_HMAC_SECRET", "test-secret-key")

    otp_service = Mock()
    cache = Mock(spec=CacheBaseAdaptor)

    otp_management = OTPManagement(
        otp_service=otp_service,
        cache=cache,
    )

    return otp_management, otp_service, cache


# --------------------------------------------------
# OTP GENERATION AND STORAGE TESTS
# --------------------------------------------------

def test_generate_otp_returns_six_digits(otp_dependencies):
    otp_management, _, _ = otp_dependencies

    otp = otp_management._generate_otp()

    assert len(otp) == 6
    assert otp.isdigit()


def test_send_otp_stores_otp_with_60_second_expiry(otp_dependencies):
    otp_management, otp_service, cache = otp_dependencies

    mobile = "9876543210"

    result = otp_management.send_otp(mobile)

    assert result is True

    otp_service.send_otp.assert_called_once()

    sent_mobile, sent_otp = otp_service.send_otp.call_args.args

    assert sent_mobile == mobile
    assert len(sent_otp) == 6

    cache.set.assert_called_once()

    key, stored_value = cache.set.call_args.args[:2]
    ttl = cache.set.call_args.kwargs["ttl"]

    stored_data = json.loads(stored_value)

    assert key == otp_management._get_otp_key(mobile)
    assert stored_data["otp_hash"] == otp_management._hash_otp(
        mobile, sent_otp
    )
    assert stored_data["failed_attempts"] == 0
    assert ttl == 60


def test_send_otp_rejects_invalid_mobile(otp_dependencies):
    otp_management, otp_service, cache = otp_dependencies

    with pytest.raises(ValueError, match="Invalid Indian mobile number"):
        otp_management.send_otp("1234567890")

    otp_service.send_otp.assert_not_called()
    cache.set.assert_not_called()


def test_send_otp_handles_provider_failure(otp_dependencies):
    otp_management, otp_service, cache = otp_dependencies

    otp_service.send_otp.side_effect = Exception("Provider unavailable")

    with pytest.raises(OTPDeliveryError):
        otp_management.send_otp("9876543210")

    cache.delete.assert_called_once_with(
        otp_management._get_otp_key("9876543210")
    )


# --------------------------------------------------
# SUCCESSFUL OTP VERIFICATION
# --------------------------------------------------

def test_verify_otp_success(otp_dependencies):
    otp_management, _, cache = otp_dependencies

    mobile = "9876543210"
    otp = "123456"

    cache.execute_atomic.return_value = [1, 0]

    result = otp_management.verify_otp(mobile, otp)

    assert result is True

    cache.execute_atomic.assert_called_once_with(
        script=otp_management.VERIFY_OTP_SCRIPT,
        keys=[otp_management._get_otp_key(mobile)],
        args=[
            otp_management._hash_otp(mobile, otp),
            5,
        ],
    )


# --------------------------------------------------
# FAILED OTP VERIFICATION
# --------------------------------------------------

def test_verify_otp_incorrect_otp(otp_dependencies):
    otp_management, _, cache = otp_dependencies

    cache.execute_atomic.return_value = [0, 1]

    result = otp_management.verify_otp(
        "9876543210",
        "111111",
    )

    assert result is False


def test_verify_otp_fifth_failed_attempt(otp_dependencies):
    otp_management, _, cache = otp_dependencies

    cache.execute_atomic.return_value = [0, 5]

    result = otp_management.verify_otp(
        "9876543210",
        "111111",
    )

    assert result is False

    # Redis Lua script handles deletion after the fifth failure.
    # Python should not separately delete the OTP.
    cache.delete.assert_not_called()


# --------------------------------------------------
# EXPIRED OTP AND OTP REUSE
# --------------------------------------------------

def test_verify_otp_expired_or_missing(otp_dependencies):
    otp_management, _, cache = otp_dependencies

    cache.execute_atomic.return_value = [-1, 0]

    result = otp_management.verify_otp(
        "9876543210",
        "123456",
    )

    assert result is False


def test_verify_otp_cannot_be_reused(otp_dependencies):
    otp_management, _, cache = otp_dependencies

    mobile = "9876543210"
    otp = "123456"

    # First verification succeeds.
    cache.execute_atomic.return_value = [1, 0]

    first_result = otp_management.verify_otp(mobile, otp)

    # Second verification finds no OTP in Redis.
    cache.execute_atomic.return_value = [-1, 0]

    second_result = otp_management.verify_otp(mobile, otp)

    assert first_result is True
    assert second_result is False

    assert cache.execute_atomic.call_count == 2


# --------------------------------------------------
# INVALID INPUT TESTS
# --------------------------------------------------

@pytest.mark.parametrize(
    "mobile",
    [
        "1234567890",
        "987654321",
        "98765432100",
        "abcdefghij",
        "",
    ],
)
def test_verify_otp_rejects_invalid_mobile(
    otp_dependencies,
    mobile,
):
    otp_management, _, cache = otp_dependencies

    with pytest.raises(ValueError, match="Invalid Indian mobile number"):
        otp_management.verify_otp(mobile, "123456")

    cache.execute_atomic.assert_not_called()


@pytest.mark.parametrize(
    "otp",
    [
        "12345",
        "1234567",
        "abcdef",
        "",
        "12 456",
    ],
)
def test_verify_otp_rejects_invalid_otp(
    otp_dependencies,
    otp,
):
    otp_management, _, cache = otp_dependencies

    with pytest.raises(ValueError, match="six digits"):
        otp_management.verify_otp("9876543210", otp)

    cache.execute_atomic.assert_not_called()


# --------------------------------------------------
# REDIS SCRIPT ERROR HANDLING
# --------------------------------------------------

def test_verify_otp_invalid_cached_data(otp_dependencies):
    otp_management, _, cache = otp_dependencies

    cache.execute_atomic.return_value = [-2, 0]

    with pytest.raises(RuntimeError, match="Invalid OTP data"):
        otp_management.verify_otp(
            "9876543210",
            "123456",
        )


def test_verify_otp_unexpected_redis_response(otp_dependencies):
    otp_management, _, cache = otp_dependencies

    cache.execute_atomic.return_value = [99, 0]

    with pytest.raises(RuntimeError, match="Unexpected OTP verification"):
        otp_management.verify_otp(
            "9876543210",
            "123456",
        )
