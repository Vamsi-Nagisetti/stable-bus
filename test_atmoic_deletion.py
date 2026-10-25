
from unittest.mock import patch

from sqlalchemy.exc import SQLAlchemyError

from core.database import SessionLocal
from models.User import User
from Repositories.UserRepository import UserRepository


def run_tests():
    database = SessionLocal()
    user_repository = UserRepository(database)
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

        original_user = user_repository.get_by_id(test_user.id)
        assert original_user.is_deletion_requested is False
        assert original_user.deletion_requested_at is None
        print("Initial account state verified: PASSED")

        # Simulate a failure during the session UPDATE.
        with patch.object(
            database,
            "execute",
            side_effect=SQLAlchemyError("Simulated database failure"),
        ):
            try:
                user_repository.request_deletion_and_revoke_sessions(
                    test_user.id
                )
            except RuntimeError:
                print("Simulated database failure handled: PASSED")
            else:
                raise AssertionError(
                    "Expected the deletion transaction to fail"
                )

        # Read the account again after the failed transaction.
        database.expire_all()
        updated_user = user_repository.get_by_id(test_user.id)

        assert updated_user.is_deletion_requested is False
        assert updated_user.deletion_requested_at is None

        print("Account deletion rolled back: PASSED")
        print("\nALL ROLLBACK TESTS PASSED")

    finally:
        try:
            if test_user is not None:
                user_repository.delete_by_id(test_user.id)
        finally:
            database.close()


if __name__ == "__main__":
    run_tests()
