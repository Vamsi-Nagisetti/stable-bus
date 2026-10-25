
from datetime import datetime, timedelta, timezone

from core.database import SessionLocal
from models.User import User
from Management.SessionManagement import SessionManagement
from Repositories.UserRepository import UserRepository
from Repositories.SessionRepository import SessionRepository


def run_tests():
    database = SessionLocal()
    user_repository = UserRepository(database)
    session_repository = SessionRepository(database)
    session_management = SessionManagement()

    test_mobile = "9123456787"
    test_user = None
    session_id = None

    try:
        # Use a dedicated test user.
        existing_user = user_repository.get_by_mobile_number(test_mobile)
        if existing_user is not None:
            raise RuntimeError(
                "Test mobile number already exists. Choose another test number."
            )

        test_user = user_repository.save(
            User(mobile_number=test_mobile)
        )

        # TEST 1: Create a refresh session.
        raw_refresh_token = session_management.create_refresh_session(
            user_id=test_user.id,
            session_repository=session_repository,
        )

        token_hash = session_management.hash_refresh_token(
            raw_refresh_token
        )
        session = session_repository.get_by_refresh_token_hash(token_hash)

        assert session is not None
        assert session.user_id == test_user.id
        assert session.refresh_token_hash != raw_refresh_token
        assert session.expires_at > datetime.now(timezone.utc)

        session_id = session.id
        print("Refresh session created: PASSED")
        print("Raw token not stored in database: PASSED")

        # TEST 2: Refresh the session.
        result = session_management.refresh_session(
            raw_refresh_token,
            session_repository,
        )

        new_access_token = result["access_token"]
        new_refresh_token = result["refresh_token"]

        claims = session_management.verify_access_token(
            new_access_token
        )

        assert claims["sub"] == str(test_user.id)
        assert new_refresh_token != raw_refresh_token

        print("Refresh produces new access token: PASSED")
        print("Refresh token rotated: PASSED")

        # TEST 3: The new refresh token should work.
        new_hash = session_management.hash_refresh_token(
            new_refresh_token
        )
        new_session = session_repository.get_by_refresh_token_hash(
            new_hash
        )

        assert new_session is not None
        assert new_session.id == session_id

        print("New refresh token maps to same session: PASSED")

        # TEST 4: Reusing the old token should be rejected.
        try:
            session_management.refresh_session(
                raw_refresh_token,
                session_repository,
            )
            raise AssertionError(
                "Previously used refresh token was accepted"
            )
        except ValueError as exc:
            if str(exc) == "Previously used refresh token was accepted":
                raise

        # The implementation should revoke the session on reuse.
        database.expire_all()
        session = database.get(
            __import__("models.UserSession", fromlist=["UserSession"]).UserSession,
            session_id,
        )

        assert session is not None
        assert session.revoked is True

        print("Reused refresh token rejected: PASSED")
        print("Session revoked after token reuse: PASSED")

    finally:
        # Remove only test data created by this test.
        if test_user is not None:
            user_repository.delete_by_id(test_user.id)

        database.close()


if __name__ == "__main__":
    run_tests()
