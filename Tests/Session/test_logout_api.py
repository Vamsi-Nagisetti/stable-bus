
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

    yield client, user_management

    app.dependency_overrides.clear()


def test_logout_success(setup_client):
    client, user_management = setup_client

    user_management.user_logout.return_value = True

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "valid-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Logged out successfully",
    }

    user_management.user_logout.assert_called_once_with(
        refresh_token="valid-refresh-token"
    )


def test_logout_invalid_token(setup_client):
    client, user_management = setup_client

    user_management.user_logout.return_value = False

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "invalid-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_logout_already_revoked_token(setup_client):
    client, user_management = setup_client

    user_management.user_logout.return_value = False

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "already-revoked-token"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_logout_missing_refresh_token(setup_client):
    client, user_management = setup_client

    response = client.post(
        "/api/v1/auth/logout",
        json={},
    )

    assert response.status_code == 422
    user_management.user_logout.assert_not_called()


def test_logout_empty_refresh_token(setup_client):
    client, user_management = setup_client

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": ""},
    )

    assert response.status_code == 422
    user_management.user_logout.assert_not_called()
