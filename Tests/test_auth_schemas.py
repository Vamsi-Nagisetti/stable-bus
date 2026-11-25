import pytest
from pydantic import ValidationError

from api.Schemas.AuthSchemas import SendOTPRequest, SendOTPResponse


def test_valid_mobile_number():
    request = SendOTPRequest(mobile_number="9876543210")
    assert request.mobile_number == "9876543210"


@pytest.mark.parametrize("mobile", [
    "1234567890",
    "987654321",
    "98765432101",
    "abcdefghij",
    "",
])
def test_invalid_mobile_numbers(mobile):
    with pytest.raises(ValidationError):
        SendOTPRequest(mobile_number=mobile)


def test_unexpected_fields_rejected():
    with pytest.raises(ValidationError):
        SendOTPRequest(
            mobile_number="9876543210",
            name="Test"
        )


def test_send_otp_response():
    response = SendOTPResponse(
        success=True,
        message="OTP sent successfully",
        expires_in=60,
        request_id="test-request-id"
    )

    assert response.success is True
    assert response.expires_in == 60