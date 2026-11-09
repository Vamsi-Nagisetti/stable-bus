
from models.User import User
from datetime import datetime, timedelta, timezone


class UserManagement:

    def __init__(
        self,
        user_repository: object,
        otp_management: object,
        session_management: object,
        session_repository: object,
    ):
        self.user_repository = user_repository
        self.otp_management = otp_management
        self.session_management = session_management
        self.session_repository = session_repository

    def verify_otp_and_login(self, mobile_number: str, otp: str):

        # 1. Verify OTP first
        is_valid = self.otp_management.verify_otp(
            mobile_number,
            otp,
        )

        if not is_valid:
            raise ValueError("Invalid or expired OTP")

        # 2. Find the user
        user = self.user_repository.get_by_mobile_number(
            mobile_number
        )

        # 3. Register a new user if this is their first login
        if user is None:
            new_user = User(mobile_number=mobile_number)

            try:
                user = self.user_repository.save(new_user)

            except ValueError:
                # Another request may have registered this mobile number.
                user = self.user_repository.get_by_mobile_number(
                    mobile_number
                )

                if user is None:
                    raise

        # 4. Handle accounts marked for deletion
        if user.is_deletion_requested:

            if user.deletion_requested_at is None:
                raise RuntimeError(
                    "Account deletion timestamp is missing"
                )

            deletion_time = user.deletion_requested_at

            if deletion_time.tzinfo is None:
                deletion_time = deletion_time.replace(
                    tzinfo=timezone.utc
                )

            deadline = deletion_time + timedelta(days=30)

            if datetime.now(timezone.utc) >= deadline:
                raise ValueError(
                    "Account deletion period has expired"
                )

            # Restore the account within the grace period
            restored = self.restore_account(user.id)

            if not restored:
                raise ValueError("Unable to restore account")

            # Fetch the restored user
            user = self.user_repository.get_by_id(user.id)

            if user is None:
                raise RuntimeError(
                    "User not found after account restoration"
                )

        # 5. Generate tokens after account checks
        access_token = self.session_management.create_access_token(
            user.id
        )

        refresh_token = self.session_management.create_refresh_session(
            user.id,
            self.session_repository,
        )

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
        }

    def request_account_deletion(self, user_id: int):
        return self.user_repository.request_deletion_and_revoke_sessions(
            user_id
        )

    def restore_account(self, user_id: int):

        user = self.user_repository.get_by_id(user_id)

        if user is None:
            return False

        if not user.is_deletion_requested:
            return True

        if user.deletion_requested_at is None:
            raise RuntimeError(
                "Account deletion timestamp is missing"
            )

        deletion_time = user.deletion_requested_at

        if deletion_time.tzinfo is None:
            deletion_time = deletion_time.replace(
                tzinfo=timezone.utc
            )

        deadline = deletion_time + timedelta(days=30)

        if datetime.now(timezone.utc) >= deadline:
            return False

        self.user_repository.restore_account(user_id)

        return True

    def permanently_delete_expired_accounts(self) -> int:
        return self.user_repository.permanently_delete_expired_accounts()

    def user_logout(self, refresh_token: str) -> bool:
        return self.session_management.logout(
            refresh_token,
            self.session_repository,
        )
    
    def refresh_user_session(self, refresh_token: str) -> dict:
        return self.session_management.refresh_session(
            refresh_token=refresh_token,
            session_repository=self.session_repository,
        )