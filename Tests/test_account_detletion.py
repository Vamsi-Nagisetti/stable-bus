
from datetime import datetime, timedelta, timezone

from Management.UserManagement import UserManagement
from Management.OtpMangement import OTPManagement
from Management.SessionManagement import SessionManagement
from Repositories.UserRepository import UserRepository
from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor
from core.database import SessionLocal
from models.User import User


class MockOTPService:
    def send_otp(self, mobile_number: str, otp: str) -> bool:
        self.last_otp = otp
        return True


def run_tests():
    database = SessionLocal()
    redis_adaptee = RedisCacheAdaptee()
    test_mobile_numbers = [
        "9123456781",
        "9123456782",
        "9123456783",
    ]

    try:
        cache = RedisCacheAdaptor(redis_adaptee)
        otp_service = MockOTPService()
        otp_management = OTPManagement(otp_service, cache)
        user_repository = UserRepository(database)
        session_management = SessionManagement()

        user_management = UserManagement(
            user_repository,
            otp_management,
            session_management,
        )

        # Ensure these dedicated test numbers are not already in use.
        for mobile in test_mobile_numbers:
            existing_user = user_repository.get_by_mobile_number(mobile)
            if existing_user is not None:
                raise RuntimeError(
                    f"Test number {mobile} already exists. "
                    "Choose a different test number."
                )

        created_user_ids = []

        try:
            # TEST 1: Normal login
            mobile = test_mobile_numbers[0]
            otp_management.send_otp(mobile)
            result = user_management.verify_otp_and_login(
                mobile, otp_service.last_otp
            )
            user = result["user"]
            created_user_ids.append(user.id)

            assert not user.is_deletion_requested
            assert session_management.verify_access_token(
                result["access_token"]
            )["sub"] == str(user.id)

            print("Normal login: PASSED")

            # TEST 2: Login within the 30-day grace period restores account
            mobile = test_mobile_numbers[1]
            user = user_repository.save(User(mobile_number=mobile))
            created_user_ids.append(user.id)

            user.is_deletion_requested = True
            user.deletion_requested_at = (
                datetime.now(timezone.utc) - timedelta(days=10)
            )
            database.commit()

            otp_management.send_otp(mobile)
            result = user_management.verify_otp_and_login(
                mobile, otp_service.last_otp
            )

            restored_user = user_repository.get_by_id(user.id)
            assert not restored_user.is_deletion_requested
            assert restored_user.deletion_requested_at is None
            assert result["user"].id == user.id

            print("Login within 30 days restores account: PASSED")

            # TEST 3: Login after the 30-day grace period is rejected
            mobile = test_mobile_numbers[2]
            user = user_repository.save(User(mobile_number=mobile))
            created_user_ids.append(user.id)

            user.is_deletion_requested = True
            user.deletion_requested_at = (
                datetime.now(timezone.utc) - timedelta(days=31)
            )
            database.commit()

            otp_management.send_otp(mobile)

            try:
                user_management.verify_otp_and_login(
                    mobile, otp_service.last_otp
                )
                raise AssertionError(
                    "Expired account was allowed to log in"
                )
            except ValueError as exc:
                if str(exc) == "Expired account was allowed to log in":
                    raise
                print("Login after 30 days rejected: PASSED")

            # Confirm the expired account remains marked for deletion.
            expired_user = user_repository.get_by_id(user.id)
            assert expired_user.is_deletion_requested

            print("Expired account remains marked for deletion: PASSED")

        finally:
            # Remove only the users created by this test.
            for user_id in created_user_ids:
                user_repository.delete_by_id(user_id)

            # Remove test OTPs from Redis.
            for mobile in test_mobile_numbers:
                cache.delete(f"stablebus:otp:{mobile}")

    finally:
        database.close()
        redis_adaptee.close()


if __name__ == "__main__":
    run_tests()
