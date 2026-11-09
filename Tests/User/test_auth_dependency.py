
import jwt
import pytest

from unittest.mock import Mock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import api.dependencies.auth as auth_dependencies


@pytest.fixture
def setup_client(monkeypatch):
    app = FastAPI()

    session_management = Mock()
    app.state.session_management = session_management

    db = Mock()
    user_repository = Mock()

    monkeypatch.setattr(
        auth_dependencies,
        "UserRepository",
        lambda database: user_repository,
    )

    app.dependency_overrides[auth_dependencies.get_db] = (
        lambda: db
    )

    @app.get("/protected")
    def protected_route(
        current_user=Depends(auth_dependencies.get_current_user),
    ):
        return {
            "user_id": current_user.id,
            "mobile_number": current_user.mobile_number,
        }

    client = TestClient(app)

    yield client, session_management, user_repository

    app.dependency_overrides.clear()


def test_missing_access_token(setup_client):
    client, session_management, user_repository = setup_client

    response = client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"

    session_management.verify_access_token.assert_not_called()
    user_repository.get_by_id.assert_not_called()


def test_invalid_access_token(setup_client):
    client, session_management, user_repository = setup_client

    session_management.verify_access_token.side_effect = (
        jwt.InvalidTokenError("Invalid token")
    )

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid or expired access token"
    )

    user_repository.get_by_id.assert_not_called()


def test_expired_access_token(setup_client):
    client, session_management, user_repository = setup_client

    session_management.verify_access_token.side_effect = (
        jwt.ExpiredSignatureError("Token expired")
    )

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer expired-token"},
    )

    assert response.status_code == 401

    user_repository.get_by_id.assert_not_called()


def test_valid_access_token(setup_client):
    client, session_management, user_repository = setup_client

    user = Mock()
    user.id = 3
    user.mobile_number = "9876543210"
    user.is_deletion_requested = False

    session_management.verify_access_token.return_value = {
        "sub": "3"
    }

    user_repository.get_by_id.return_value = user

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200

    assert response.json() == {
        "user_id": 3,
        "mobile_number": "9876543210",
    }

    session_management.verify_access_token.assert_called_once_with(
        "valid-token"
    )

    user_repository.get_by_id.assert_called_once_with(3)


def test_user_not_found(setup_client):
    client, session_management, user_repository = setup_client

    session_management.verify_access_token.return_value = {
        "sub": "999"
    }

    user_repository.get_by_id.return_value = None

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "User not found"

    user_repository.get_by_id.assert_called_once_with(999)


def test_user_with_deletion_requested_is_forbidden(setup_client):
    client, session_management, user_repository = setup_client

    user = Mock()
    user.id = 3
    user.mobile_number = "9876543210"
    user.is_deletion_requested = True

    session_management.verify_access_token.return_value = {
        "sub": "3"
    }

    user_repository.get_by_id.return_value = user

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Account deletion requested. Account access is restricted."
    )

    user_repository.get_by_id.assert_called_once_with(3)
