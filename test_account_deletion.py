
from core.database import SessionLocal
from models.User import User
from models.UserSession import UserSession
from Repositories.UserRepository import UserRepository
from Repositories.SessionRepository import SessionRepository
from Management.SessionManagement import SessionManagement
from Management.UserManagement import UserManagement


class FakeOTPManagement:
    def verify_otp(self, mobile_number, otp):
        return True


def run_tests():
    database = SessionLocal()
    user_repository = UserRepository(database)
    session_repository = SessionRepository(database)
    session_management = SessionManagement()

    user_management = UserManagement(
        user_repository,
        FakeOTPManagement(),
        session_management,
        session_repository,
    )

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

        # Simulate three devices logged into the same account.
        tokens = [
            session_management.create_refresh_session(
                test_user.id, session_repository
            )
            for _ in range(3)
        ]

        hashes = [
            session_management.hash_refresh_token(token)
            for token in tokens
        ]

        print("Three device sessions created: PASSED")

        # Request account deletion.
        result = user_management.request_account_deletion(
            test_user.id
        )
        assert result is True

        database.expire_all()
        updated_user = user_repository.get_by_id(test_user.id)
        assert updated_user.is_deletion_requested is True
        assert updated_user.deletion_requested_at is not None
        print("Account marked for deletion: PASSED")

        # Every refresh session should now be revoked.
        for token_hash in hashes:
            session = session_repository.get_by_refresh_token_hash(
                token_hash
            )
            assert session is not None
            assert session.revoked is True

        print("All device sessions revoked: PASSED")

        # None of the old refresh tokens should work.
        for token in tokens:
            try:
                session_management.refresh_session(
                    token, session_repository
                )
            except ValueError:
                continue
            else:
                raise AssertionError(
                    "A refresh token worked after account deletion"
                )

        print("Old refresh tokens rejected: PASSED")

        # Repeating the request should remain safe.
        assert user_management.request_account_deletion(
            test_user.id
        ) is True
        print("Repeated deletion request handled safely: PASSED")

        print("\nALL ACCOUNT DELETION SESSION TESTS PASSED")

    finally:
        try:
            if test_user is not None:
                user_repository.delete_by_id(test_user.id)
        finally:
            database.close()


if __name__ == "__main__":
    run_tests()
