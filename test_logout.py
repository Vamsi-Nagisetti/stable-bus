
from datetime import datetime, timedelta, timezone

from core.database import SessionLocal
from models.User import User
from models.UserSession import UserSession
from Repositories.UserRepository import UserRepository
from Repositories.SessionRepository import SessionRepository
from Management.SessionManagement import SessionManagement


def run_tests():
    database = SessionLocal()
    user_repository = UserRepository(database)
    session_repository = SessionRepository(database)
    session_management = SessionManagement()

    test_mobile = "9123456787"
    test_user = None

    try:
        if user_repository.get_by_mobile_number(test_mobile):
            raise RuntimeError(
                "Test mobile already exists. Choose another test number."
            )

        test_user = user_repository.save(
            User(mobile_number=test_mobile)
        )

        # Test 1: An expired refresh session must be rejected.
        expired_token = session_management.create_refresh_session(
            test_user.id, session_repository
        )
        expired_hash = session_management.hash_refresh_token(
            expired_token
        )
        expired_session = session_repository.get_by_refresh_token_hash(
            expired_hash
        )

        expired_session.expires_at = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        database.commit()

        try:
            session_management.refresh_session(
                expired_token, session_repository
            )
        except ValueError:
            print("Expired refresh token rejected: PASSED")
        else:
            raise AssertionError("Expired refresh token was accepted")

        # Test 2: A revoked session must not refresh.
        revoked_token = session_management.create_refresh_session(
            test_user.id, session_repository
        )
        revoked_hash = session_management.hash_refresh_token(
            revoked_token
        )
        revoked_session = session_repository.get_by_refresh_token_hash(
            revoked_hash
        )

        assert session_repository.revoke(revoked_session.id) is True

        try:
            session_management.refresh_session(
                revoked_token, session_repository
            )
        except ValueError:
            print("Revoked session cannot refresh: PASSED")
        else:
            raise AssertionError("Revoked session was refreshed")

        # Test 3: An unknown token must be rejected.
        try:
            session_management.refresh_session(
                "invalid-test-refresh-token", session_repository
            )
        except ValueError:
            print("Invalid refresh token rejected: PASSED")
        else:
            raise AssertionError("Invalid refresh token was accepted")

        # Test 4: A valid refresh token should still work.
        valid_token = session_management.create_refresh_session(
            test_user.id, session_repository
        )
        valid_result = session_management.refresh_session(
            valid_token, session_repository
        )

        assert valid_result["access_token"]
        assert valid_result["refresh_token"]
        assert valid_result["refresh_token"] != valid_token
        print("Valid refresh token works normally: PASSED")

        print("\nALL SESSION EDGE-CASE TESTS PASSED")

    finally:
        try:
            if test_user is not None:
                user_repository.delete_by_id(test_user.id)
        finally:
            database.close()


if __name__ == "__main__":
    run_tests()
