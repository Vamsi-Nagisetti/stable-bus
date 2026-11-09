
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from Management.UserManagement import UserManagement


@pytest.fixture
def dependencies():
    user_repository = MagicMock()
    otp_management = MagicMock()
    session_management = MagicMock()
    session_repository = MagicMock()

    management = UserManagement(
        user_repository=user_repository,
        otp_management=otp_management,
        session_management=session_management,
        session_repository=session_repository,
    )

    return management, user_repository, otp_management, session_management


def test_new_user_registration_and_login(dependencies):
    management, repo, otp, sessions = dependencies

    otp.verify_otp.return_value = True
    repo.get_by_mobile_number.return_value = None

    def save_user(user):
        user.id = 101
        user.is_deletion_requested = False
        return user

    repo.save.side_effect = save_user

    sessions.create_access_token.return_value = "access-token"
    sessions.create_refresh_session.return_value = "refresh-token"

    result = management.verify_otp_and_login(
        "9876543210",
        "123456",
    )

    assert result["user"].id == 101
    assert result["access_token"] == "access-token"
    assert result["refresh_token"] == "refresh-token"
    assert result["token_type"] == "Bearer"

    repo.save.assert_called_once()
    sessions.create_access_token.assert_called_once_with(101)


def test_existing_user_login(dependencies):
    management, repo, otp, sessions = dependencies

    existing_user = SimpleNamespace(
        id=202,
        is_deletion_requested=False,
        deletion_requested_at=None,
    )

    otp.verify_otp.return_value = True
    repo.get_by_mobile_number.return_value = existing_user

    sessions.create_access_token.return_value = "access-token"
    sessions.create_refresh_session.return_value = "refresh-token"

    result = management.verify_otp_and_login(
        "9876543210",
        "123456",
    )

    assert result["user"] is existing_user
    repo.save.assert_not_called()
    sessions.create_access_token.assert_called_once_with(202)


def test_invalid_otp_does_not_create_user(dependencies):
    management, repo, otp, sessions = dependencies

    otp.verify_otp.return_value = False

    with pytest.raises(ValueError, match="Invalid or expired OTP"):
        management.verify_otp_and_login(
            "9876543210",
            "123456",
        )

    repo.get_by_mobile_number.assert_not_called()
    repo.save.assert_not_called()
    sessions.create_access_token.assert_not_called()


def test_expired_deletion_period_blocks_login(dependencies):
    management, repo, otp, sessions = dependencies

    deleted_user = SimpleNamespace(
        id=303,
        is_deletion_requested=True,
        deletion_requested_at=(
            datetime.now(timezone.utc) - timedelta(days=31)
        ),
    )

    otp.verify_otp.return_value = True
    repo.get_by_mobile_number.return_value = deleted_user

    with pytest.raises(ValueError, match="Account deletion period has expired"):
        management.verify_otp_and_login(
            "9876543210",
            "123456",
        )

    sessions.create_access_token.assert_not_called()
    sessions.create_refresh_session.assert_not_called()

def test_account_restored_within_grace_period(dependencies):
    management, repo, otp, sessions = dependencies

    deleted_user = SimpleNamespace(
        id=404,
        is_deletion_requested=True,
        deletion_requested_at=(
            datetime.now(timezone.utc) - timedelta(days=10)
        ),
    )

    restored_user = SimpleNamespace(
        id=404,
        is_deletion_requested=False,
        deletion_requested_at=None,
    )

    otp.verify_otp.return_value = True
    repo.get_by_mobile_number.return_value = deleted_user
    repo.get_by_id.side_effect = [
    deleted_user,   # First call: account still marked for deletion
    restored_user,  # Second call: account has been restored
]
    sessions.create_access_token.return_value = "access-token"
    sessions.create_refresh_session.return_value = "refresh-token"

    result = management.verify_otp_and_login(
        "9876543210",
        "123456",
    )

    repo.restore_account.assert_called_once_with(404)
    assert result["user"] is restored_user
    sessions.create_access_token.assert_called_once_with(404)

def test_missing_deletion_timestamp_blocks_login(dependencies):
    management, repo, otp, sessions = dependencies

    deleted_user = SimpleNamespace(
        id=505,
        is_deletion_requested=True,
        deletion_requested_at=None,
    )

    otp.verify_otp.return_value = True
    repo.get_by_mobile_number.return_value = deleted_user

    with pytest.raises(
        RuntimeError,
        match="Account deletion timestamp is missing",
    ):
        management.verify_otp_and_login(
            "9876543210",
            "123456",
        )

    sessions.create_access_token.assert_not_called()
    sessions.create_refresh_session.assert_not_called()