
import pytest
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.auth import router
from Management.RateLimitManagement import RateLimitExceededError


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    mock_orchestrator = Mock()
    app.state.auth_orchestrator = mock_orchestrator

    app.state.auth_orchestrator.send_otp.return_value = True

    return TestClient(app), mock_orchestrator


def test_send_otp_success(client):
    test_client, orchestrator = client

    response = test_client.post(
        "/api/v1/auth/send-otp",
        json={"mobile_number": "9876543210"}
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["message"] == "OTP sent successfully"
    assert data["expires_in"] == 60
    assert "request_id" in data

    orchestrator.send_otp.assert_called_once()


def test_send_otp_invalid_mobile(client):
    test_client, orchestrator = client

    response = test_client.post(
        "/api/v1/auth/send-otp",
        json={"mobile_number": "1234567890"}
    )

    assert response.status_code == 422
    orchestrator.send_otp.assert_not_called()


def test_send_otp_rate_limit(client):
    test_client, orchestrator = client

    orchestrator.send_otp.side_effect = RateLimitExceededError(
        message="OTP request limit exceeded",
        retry_after=30
    )

    response = test_client.post(
        "/api/v1/auth/send-otp",
        json={"mobile_number": "9876543210"}
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["retry_after"] == 30


def test_send_otp_delivery_failure(client):
    test_client, orchestrator = client

    orchestrator.send_otp.side_effect = RuntimeError(
        "Unable to send OTP"
    )

    response = test_client.post(
        "/api/v1/auth/send-otp",
        json={"mobile_number": "9876543210"}
    )

    assert response.status_code == 503


def test_send_otp_missing_mobile(client):
    test_client, orchestrator = client

    response = test_client.post(
        "/api/v1/auth/send-otp",
        json={}
    )

    assert response.status_code == 422
    orchestrator.send_otp.assert_not_called()
