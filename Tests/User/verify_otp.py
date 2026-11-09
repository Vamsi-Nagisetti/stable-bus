
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.auth import router
from api.dependencies.auth import get_user_management


@pytest.fixture
def setup_client():
    app = FastAPI()
    app.include_router(router)

    user_management = MagicMock()

    app.dependency_overrides[get_user_management] = (
        lambda: user_management
    )

    client = TestClient(app)

    return client, user_management


def test_verify_otp_success(setup_client):
    client, user_management = setup_client

    user_management.verify_otp_and_login.return_value = {
        "user": MagicMock(id=101),
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "token_type": "Bearer",
    }

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "mobile_number": "9876543210",
            "otp": "123456",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["message"] == "Login successful"
    assert data["access_token"] == "test-access-token"
    assert data["refresh_token"] == "test-refresh-token"
    assert data["token_type"] == "Bearer"

    user_management.verify_otp_and_login.assert_called_once_with(
        mobile_number="9876543210",
        otp="123456",
    )


def test_verify_otp_invalid_otp(setup_client):
    client, user_management = setup_client

    user_management.verify_otp_and_login.side_effect = ValueError(
        "Invalid or expired OTP"
    )

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "mobile_number": "9876543210",
            "otp": "123456",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"]["message"] == (
        "Invalid or expired OTP"
    )


def test_verify_otp_invalid_request(setup_client):
    client, user_management = setup_client

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "mobile_number": "123",
            "otp": "12",
        },
    )

    assert response.status_code == 422

    user_management.verify_otp_and_login.assert_not_called()


def test_verify_otp_missing_fields(setup_client):
    client, user_management = setup_client

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "mobile_number": "9876543210",
        },
    )

    assert response.status_code == 422

    user_management.verify_otp_and_login.assert_not_called()
