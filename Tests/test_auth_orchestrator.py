
from unittest.mock import Mock
from Management.OtpMangement import OTPDeliveryError

import pytest

from Orchestrators.AuthOrchestrator import AuthOrchestrator
from Management.RateLimitManagement import RateLimitExceededError


@pytest.fixture
def auth_dependencies():
    otp_management = Mock()
    rate_limit_management = Mock()

    orchestrator = AuthOrchestrator(
        otp_management=otp_management,
        rate_limit_management=rate_limit_management
    )

    return orchestrator, otp_management, rate_limit_management


def test_send_otp_success(auth_dependencies):
    orchestrator, otp_management, rate_limit_management = (
        auth_dependencies
    )

    otp_management.send_otp.return_value = True

    result = orchestrator.send_otp(
        mobile_number="9876543210",
        client_ip="127.0.0.1"
    )

    assert result is True

    rate_limit_management.check_otp_request.assert_called_once_with(
        "9876543210",
        "127.0.0.1"
    )

    otp_management.send_otp.assert_called_once_with("9876543210")

    rate_limit_management.clear_otp_cooldown.assert_not_called()


def test_rate_limit_rejection_does_not_send_otp(auth_dependencies):
    orchestrator, otp_management, rate_limit_management = (
        auth_dependencies
    )

    rate_limit_management.check_otp_request.side_effect = (
        RateLimitExceededError("Rate limit exceeded", 30)
    )

    with pytest.raises(RateLimitExceededError):
        orchestrator.send_otp(
            "9876543210",
            "127.0.0.1"
        )

    otp_management.send_otp.assert_not_called()
    rate_limit_management.clear_otp_cooldown.assert_not_called()


def test_sms_failure_clears_cooldown(auth_dependencies):
    orchestrator, otp_management, rate_limit_management = (
        auth_dependencies
    )

    otp_management.send_otp.side_effect = OTPDeliveryError("Unable to send OTP")

    with pytest.raises(OTPDeliveryError):
        orchestrator.send_otp(
            "9876543210",
            "127.0.0.1"
        )

    rate_limit_management.check_otp_request.assert_called_once()
    otp_management.send_otp.assert_called_once_with("9876543210")

    rate_limit_management.clear_otp_cooldown.assert_called_once_with(
        "9876543210"
    )


def test_sms_failure_preserves_original_exception(auth_dependencies):
    orchestrator, otp_management, rate_limit_management = (
        auth_dependencies
    )

    original_error = RuntimeError("SMS provider unavailable")
    otp_management.send_otp.side_effect = original_error

    with pytest.raises(RuntimeError) as exc:
        orchestrator.send_otp(
            "9876543210",
            "127.0.0.1"
        )

    assert exc.value is original_error


def test_success_does_not_clear_cooldown(auth_dependencies):
    orchestrator, otp_management, rate_limit_management = (
        auth_dependencies
    )

    otp_management.send_otp.return_value = True

    orchestrator.send_otp(
        "9876543210",
        "127.0.0.1"
    )

    rate_limit_management.clear_otp_cooldown.assert_not_called()
