
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from Repositories.SessionRepository import SessionRepository
from models.UserSession import UserSession


@pytest.fixture
def database():
    return Mock()


@pytest.fixture
def repository(database):
    return SessionRepository(database)


@pytest.fixture
def user_session():
    return UserSession(
        user_id=1,
        refresh_token_hash="a" * 64,
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        last_refreshed_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        expires_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        revoked=False,
    )


# --------------------------------------------------
# CREATE SESSION
# --------------------------------------------------

def test_create_session_success(repository, database, user_session):
    result = repository.create(user_session)

    database.add.assert_called_once_with(user_session)
    database.commit.assert_called_once()
    database.refresh.assert_called_once_with(user_session)

    assert result is user_session


def test_create_session_database_error(repository, database, user_session):
    database.commit.side_effect = SQLAlchemyError("Database failure")

    with pytest.raises(RuntimeError, match="Unable to create user session"):
        repository.create(user_session)

    database.rollback.assert_called_once()


# --------------------------------------------------
# GET SESSION
# --------------------------------------------------

def test_get_session_by_refresh_token_hash(repository, database):
    expected_session = Mock(spec=UserSession)

    database.execute.return_value.scalar_one_or_none.return_value = (
        expected_session
    )

    result = repository.get_by_refresh_token_hash("a" * 64)

    assert result is expected_session
    database.execute.assert_called_once()


def test_get_session_not_found(repository, database):
    database.execute.return_value.scalar_one_or_none.return_value = None

    result = repository.get_by_refresh_token_hash("b" * 64)

    assert result is None


def test_get_session_database_error(repository, database):
    database.execute.side_effect = SQLAlchemyError("Database failure")

    with pytest.raises(
        RuntimeError,
        match="Unable to retrieve user session",
    ):
        repository.get_by_refresh_token_hash("a" * 64)

    database.rollback.assert_called_once()


# --------------------------------------------------
# REVOKE SESSION
# --------------------------------------------------

def test_revoke_session_success(repository, database):
    database.execute.return_value.rowcount = 1

    result = repository.revoke(session_id=10)

    assert result is True
    database.commit.assert_called_once()


def test_revoke_session_not_found_or_already_revoked(
    repository,
    database,
):
    database.execute.return_value.rowcount = 0

    result = repository.revoke(session_id=10)

    assert result is False
    database.commit.assert_called_once()


# --------------------------------------------------
# ROTATE REFRESH TOKEN
# --------------------------------------------------

def test_rotate_refresh_token_success(repository, database):
    database.execute.return_value.rowcount = 1

    result = repository.rotate_refresh_token(
        session_id=10,
        old_token_hash="a" * 64,
        new_token_hash="b" * 64,
    )

    assert result is True
    database.commit.assert_called_once()


def test_rotate_refresh_token_failure(repository, database):
    database.execute.return_value.rowcount = 0

    result = repository.rotate_refresh_token(
        session_id=10,
        old_token_hash="a" * 64,
        new_token_hash="b" * 64,
    )

    assert result is False


def test_rotate_refresh_token_database_error(repository, database):
    database.execute.side_effect = SQLAlchemyError("Database failure")

    with pytest.raises(
        RuntimeError,
        match="Unable to rotate refresh token",
    ):
        repository.rotate_refresh_token(
            session_id=10,
            old_token_hash="a" * 64,
            new_token_hash="b" * 64,
        )

    database.rollback.assert_called_once()


# --------------------------------------------------
# REVOKE PREVIOUS REFRESH TOKEN
# --------------------------------------------------

def test_revoke_previous_token_success(repository, database):
    database.execute.return_value.rowcount = 1

    result = repository.revoke_if_previous_token_matches("a" * 64)

    assert result is True
    database.commit.assert_called_once()


def test_revoke_previous_token_not_found(repository, database):
    database.execute.return_value.rowcount = 0

    result = repository.revoke_if_previous_token_matches("a" * 64)

    assert result is False


# --------------------------------------------------
# REVOKE ALL SESSIONS FOR USER
# --------------------------------------------------

def test_revoke_all_sessions_for_user(repository, database):
    database.execute.return_value.rowcount = 3

    result = repository.revoke_all_for_user(user_id=1)

    assert result == 3
    database.commit.assert_called_once()


def test_revoke_all_sessions_when_none_exist(repository, database):
    database.execute.return_value.rowcount = 0

    result = repository.revoke_all_for_user(user_id=1)

    assert result == 0


def test_revoke_all_sessions_database_error(repository, database):
    database.execute.side_effect = SQLAlchemyError("Database failure")

    with pytest.raises(
        RuntimeError,
        match="Unable to revoke user sessions",
    ):
        repository.revoke_all_for_user(user_id=1)

    database.rollback.assert_called_once()
