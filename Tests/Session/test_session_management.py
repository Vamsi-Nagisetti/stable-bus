
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from Management.SessionManagement import SessionManagement


@pytest.fixture
def session_management():
    manager = SessionManagement.__new__(SessionManagement)

    manager.issuer = "stablebus"
    manager.audience = "stablebus-api"
    manager.access_token_minutes = 30
    manager.refresh_token_days = 90

    return manager


@pytest.fixture
def session_repository():
    return Mock()


def create_test_session(
    user_id=1,
    session_id=10,
    revoked=False,
    expires_at=None,
):
    return SimpleNamespace(
        id=session_id,
        user_id=user_id,
        revoked=revoked,
        expires_at=expires_at or (
            datetime.now(timezone.utc) + timedelta(days=10)
        ),
    )


def test_generate_refresh_token(session_management):
    token = session_management.generate_refresh_token()

    assert isinstance(token, str)
    assert len(token) > 30


def test_hash_refresh_token(session_management):
    token = "sample-refresh-token"

    hash1 = session_management.hash_refresh_token(token)
    hash2 = session_management.hash_refresh_token(token)

    assert hash1 == hash2
    assert len(hash1) == 64
    assert hash1 != token


def test_create_refresh_session(
    session_management,
    session_repository,
    monkeypatch,
):
    monkeypatch.setattr(
        session_management,
        "generate_refresh_token",
        lambda: "sample-refresh-token",
    )

    token = session_management.create_refresh_session(
        user_id=1,
        session_repository=session_repository,
    )

    assert token == "sample-refresh-token"

    session_repository.create.assert_called_once()

    saved_session = session_repository.create.call_args.args[0]

    assert saved_session.user_id == 1
    assert saved_session.refresh_token_hash == (
        session_management.hash_refresh_token(token)
    )
    assert saved_session.revoked is False
    assert saved_session.expires_at > saved_session.created_at


def test_refresh_session_success(
    session_management,
    session_repository,
    monkeypatch,
):
    old_token = "old-refresh-token"

    session = create_test_session()

    session_repository.get_by_refresh_token_hash.return_value = session
    session_repository.rotate_refresh_token.return_value = True

    monkeypatch.setattr(
        session_management,
        "generate_refresh_token",
        lambda: "new-refresh-token",
    )

    monkeypatch.setattr(
        session_management,
        "create_access_token",
        lambda user_id: "new-access-token",
    )

    result = session_management.refresh_session(
        old_token,
        session_repository,
    )

    assert result == {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "token_type": "Bearer",
    }

    session_repository.rotate_refresh_token.assert_called_once()


def test_refresh_session_invalid_token(
    session_management,
    session_repository,
):
    session_repository.get_by_refresh_token_hash.return_value = None

    with pytest.raises(ValueError, match="Invalid refresh token"):
        session_management.refresh_session(
            "invalid-token",
            session_repository,
        )

    session_repository.rotate_refresh_token.assert_not_called()


def test_refresh_session_empty_token(
    session_management,
    session_repository,
):
    with pytest.raises(ValueError, match="required"):
        session_management.refresh_session(
            "",
            session_repository,
        )


def test_refresh_session_revoked(
    session_management,
    session_repository,
):
    session = create_test_session(revoked=True)

    session_repository.get_by_refresh_token_hash.return_value = session

    with pytest.raises(ValueError, match="revoked"):
        session_management.refresh_session(
            "old-refresh-token",
            session_repository,
        )

    session_repository.rotate_refresh_token.assert_not_called()


def test_refresh_session_expired(
    session_management,
    session_repository,
):
    session = create_test_session(
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )

    session_repository.get_by_refresh_token_hash.return_value = session

    with pytest.raises(ValueError, match="expired"):
        session_management.refresh_session(
            "old-refresh-token",
            session_repository,
        )

    session_repository.rotate_refresh_token.assert_not_called()


def test_refresh_session_rotation_failure(
    session_management,
    session_repository,
    monkeypatch,
):
    session = create_test_session()

    session_repository.get_by_refresh_token_hash.return_value = session
    session_repository.rotate_refresh_token.return_value = False

    monkeypatch.setattr(
        session_management,
        "generate_refresh_token",
        lambda: "new-refresh-token",
    )

    with pytest.raises(ValueError, match="no longer valid"):
        session_management.refresh_session(
            "old-refresh-token",
            session_repository,
        )

    # Failed rotation must not automatically revoke the session.
    session_repository.revoke_if_previous_token_matches.assert_not_called()


def test_logout_success(
    session_management,
    session_repository,
):
    session = create_test_session()

    session_repository.get_by_refresh_token_hash.return_value = session
    session_repository.revoke.return_value = True

    result = session_management.logout(
        "valid-refresh-token",
        session_repository,
    )

    assert result is True
    session_repository.revoke.assert_called_once_with(session.id)


def test_logout_invalid_token(
    session_management,
    session_repository,
):
    session_repository.get_by_refresh_token_hash.return_value = None

    result = session_management.logout(
        "invalid-refresh-token",
        session_repository,
    )

    assert result is False
    session_repository.revoke.assert_not_called()


def test_logout_already_revoked(
    session_management,
    session_repository,
):
    session = create_test_session(revoked=True)

    session_repository.get_by_refresh_token_hash.return_value = session

    result = session_management.logout(
        "old-refresh-token",
        session_repository,
    )

    assert result is False
    session_repository.revoke.assert_not_called()


def test_logout_empty_token(
    session_management,
    session_repository,
):
    with pytest.raises(ValueError, match="required"):
        session_management.logout(
            "",
            session_repository,
        )
