
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.auth import router
from api.dependencies.auth import get_user_management


@pytest.fixture
def setup_client():
    app = FastAPI()
    app.include_router(router)

    user_management = Mock()

    app.dependency_overrides[get_user_management] = (
        lambda: user_management
    )

    client = TestClient(app)

    return client, user_management


def test_refresh_token_success(setup_client):
    client, user_management = setup_client

    user_management.refresh_user_session.return_value = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "token_type": "Bearer",
    }

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "valid-refresh-token"},
    )

    assert response.status_code == 200

    assert response.json() == {
        "success": True,
        "message": "Token refreshed successfully",
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "token_type": "Bearer",
    }

    user_management.refresh_user_session.assert_called_once_with(
        refresh_token="valid-refresh-token"
    )


def test_refresh_token_invalid(setup_client):
    client, user_management = setup_client

    user_management.refresh_user_session.side_effect = ValueError(
        "Invalid refresh token"
    )

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid-refresh-token"},
    )

    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["message"] == "Invalid refresh token"


def test_refresh_token_expired_session(setup_client):
    client, user_management = setup_client

    user_management.refresh_user_session.side_effect = ValueError(
        "Refresh session has expired"
    )

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "expired-refresh-token"},
    )

    assert response.status_code == 401
    assert response.json()["message"] == "Refresh session has expired"


def test_refresh_token_revoked_session(setup_client):
    client, user_management = setup_client

    user_management.refresh_user_session.side_effect = ValueError(
        "Refresh session has been revoked"
    )

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "revoked-refresh-token"},
    )

    assert response.status_code == 401
    assert response.json()["message"] == "Refresh session has been revoked"


def test_refresh_token_missing_or_empty(setup_client):
    client, user_management = setup_client

    # Missing refresh_token
    missing_response = client.post(
        "/api/v1/auth/refresh",
        json={},
    )

    assert missing_response.status_code == 422

    # Empty refresh_token
    empty_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": ""},
    )

    assert empty_response.status_code == 422

    user_management.refresh_user_session.assert_not_called()
