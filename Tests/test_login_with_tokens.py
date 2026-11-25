
from datetime import datetime, timezone

from core.database import SessionLocal
from models.User import User
from models.UserSession import UserSession
from Management.UserManagement import UserManagement
from Management.SessionManagement import SessionManagement
from Repositories.UserRepository import UserRepository
from Repositories.SessionRepository import SessionRepository


class FakeOTPManagement:
    def verify_otp(self, mobile_number, otp):
        return mobile_number == "9123456787" and otp == "123456"


def run_tests():
    database = SessionLocal()

    user_repository = UserRepository(database)
    session_repository = SessionRepository(database)
    session_management = SessionManagement()
    otp_management = FakeOTPManagement()

    user_management = UserManagement(
        user_repository,
        otp_management,
        session_management,
        session_repository,
    )

    test_mobile = "9123456787"
    test_user = None

    try:
        existing_user = user_repository.get_by_mobile_number(test_mobile)
        if existing_user is not None:
            raise RuntimeError(
                f"Test mobile {test_mobile} already exists. "
                "Change test_mobile to a number not in your database."
            )

        # 1. Login using a valid test OTP
        login_result = user_management.verify_otp_and_login(
            test_mobile, "123456"
        )
        test_user = login_result["user"]

        assert login_result["access_token"]
        assert login_result["refresh_token"]
        assert login_result["token_type"] == "Bearer"
        print("OTP login returns both tokens: PASSED")

        # 2. Verify access token
        claims = session_management.verify_access_token(
            login_result["access_token"]
        )
        assert claims["sub"] == str(test_user.id)
        print("Access token is valid: PASSED")

        # 3. Verify refresh session is saved as a hash
        raw_refresh_token = login_result["refresh_token"]
        old_hash = session_management.hash_refresh_token(
            raw_refresh_token
        )
        session = session_repository.get_by_refresh_token_hash(old_hash)

        assert session is not None
        assert session.user_id == test_user.id
        assert session.refresh_token_hash != raw_refresh_token
        assert session.revoked is False
        assert session.expires_at > datetime.now(timezone.utc)
        session_id = session.id
        print("Refresh session stored securely: PASSED")

        # 4. Refresh and rotate the refresh token
        refresh_result = session_management.refresh_session(
            raw_refresh_token, session_repository
        )

        new_access_token = refresh_result["access_token"]
        new_refresh_token = refresh_result["refresh_token"]

        assert new_access_token
        assert new_refresh_token
        assert new_refresh_token != raw_refresh_token
        session_management.verify_access_token(new_access_token)
        print("Refresh issues a new access token: PASSED")
        print("Refresh token rotation: PASSED")

        # 5. Confirm the rotated token belongs to the same session
        new_hash = session_management.hash_refresh_token(
            new_refresh_token
        )
        rotated_session = session_repository.get_by_refresh_token_hash(
            new_hash
        )

        assert rotated_session is not None
        assert rotated_session.id == session_id
        print("Rotated token retains the same session: PASSED")

        # 6. Reuse the old token; it must be rejected
        try:
            session_management.refresh_session(
                raw_refresh_token, session_repository
            )
        except ValueError:
            print("Reused refresh token rejected: PASSED")
        else:
            raise AssertionError("Reused refresh token was accepted")

        # 7. Confirm reuse detection revoked the session
        database.expire_all()
        final_session = database.get(UserSession, session_id)

        assert final_session is not None
        assert final_session.revoked is True
        print("Session revoked after token reuse: PASSED")

        print("\nALL LOGIN AND REFRESH TESTS PASSED")

    finally:
        # Remove test data, even if a test fails.
        try:
            if test_user is not None:
                user_repository.delete_by_id(test_user.id)
        finally:
            database.close()


if __name__ == "__main__":
    run_tests()
