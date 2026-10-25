from models.User import User
from datetime import datetime, timedelta, timezone


class UserManagement:

    def __init__(self, user_repository: object, otp_management: object, session_management: object, session_repository: object):
        self.user_repository = user_repository
        self.otp_management = otp_management
        self.session_management = session_management
        self.session_repository = session_repository

    
    def get_or_create_user(self, mobile_number: str):
        user = self.user_repository.get_by_mobile_number(mobile_number)

        if user is not None:
            return user

        new_user = User(mobile_number=mobile_number)
        return self.user_repository.save(new_user)


    def verify_otp_and_login(self, mobile_number: str, otp: str):
        # 1. Verify OTP first
        is_valid = self.otp_management.verify_otp(mobile_number, otp)

        if not is_valid:
            raise ValueError("Invalid or expired OTP")

        # 2. Find the user
        user = self.user_repository.get_by_mobile_number(mobile_number)

        # 3. Create a user if this is their first login
        if user is None:
            user = User(mobile_number=mobile_number)
            user = self.user_repository.save(user)

        # 4. Handle accounts marked for deletion
        if user.is_deletion_requested:
            if user.deletion_requested_at is None:
                raise RuntimeError(
                    "Account deletion timestamp is missing"
                )

            # Ensure both datetimes are timezone-aware
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

            # Within the grace period: restore the account
            restored = self.restore_account(user.id)

            if not restored:
                raise ValueError("Unable to restore account")

            # Fetch the updated user
            user = self.user_repository.get_by_id(user.id)

        # 5. Create an access token only after account checks
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

        deadline = user.deletion_requested_at + timedelta(days=30)

        if datetime.now(timezone.utc) >= deadline:
            return False

        self.user_repository.restore_account(user_id)
        return True

    
    def permanently_delete_expired_accounts(self) -> int:
        return self.user_repository.permanently_delete_expired_accounts()



    def user_login(self):
        pass

    def user_logout(self, refresh_token: str) -> bool:
        return self.session_management.logout(
            refresh_token,
            self.session_repository,
        )



