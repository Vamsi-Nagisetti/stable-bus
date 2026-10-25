from sqlalchemy import select,delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from datetime import datetime, timedelta, timezone

from models.User import User

class UserRepository:

    def __init__(self, database):
        self.database = database

    def save(self, user):
        # INSERT user record
        try:
            self.database.add(user)
            self.database.commit()
            self.database.refresh(user)
            return user
        except IntegrityError as exc:
            self.database.rollback()
            raise ValueError(
                "A user with this mobile number may already exist"
            ) from exc

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to save user due to a database error"
            ) from exc
        

   

    def get_by_id(self, user_id):

        try:
            statement = select(User).where(User.id == user_id)
            result = self.database.execute(statement)
            return result.scalar_one_or_none()

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to retrieve user due to a database error"
            ) from exc
        
    
    def delete_by_id(self , user_id):
        statement = delete(User).where(User.id == user_id)
        result = self.database.execute(statement)
        self.database.commit()
        return result.rowcount > 0

    def get_by_mobile_number(self, mobile_number: str):
        try:
            statement = select(User).where(
                User.mobile_number == mobile_number
            )
            result = self.database.execute(statement)
            return result.scalar_one_or_none()

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to retrieve user due to a database error"
            ) from exc

    
    def request_deletion(self, user_id: int):
        user = self.get_by_id(user_id)

        if user is None:
            return None

        if user.is_deletion_requested:
            return user

        user.is_deletion_requested = True
        user.deletion_requested_at = datetime.now(timezone.utc)

        try:
            self.database.commit()
            self.database.refresh(user)
            return user
        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to request account deletion"
            ) from exc


    def restore_account(self, user_id: int):
        user = self.get_by_id(user_id)

        if user is None:
            return None

        if not user.is_deletion_requested:
            return user

        user.is_deletion_requested = False
        user.deletion_requested_at = None

        try:
            self.database.commit()
            self.database.refresh(user)
            return user
        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to restore account"
            ) from exc


    def permanently_delete_expired_accounts(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        try:
            statement = delete(User).where(
                User.is_deletion_requested.is_(True),
                User.deletion_requested_at <= cutoff,
            )

            result = self.database.execute(statement)
            self.database.commit()

            return result.rowcount or 0

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to permanently delete expired accounts"
            ) from exc



    def request_deletion_and_revoke_sessions(self, user_id: int) -> bool:
        from datetime import datetime, timezone
        from sqlalchemy import update
        from sqlalchemy.exc import SQLAlchemyError
        from models.UserSession import UserSession

        try:
            user = self.get_by_id(user_id)

            if user is None:
                return False

            if user.is_deletion_requested:
                return True

            user.is_deletion_requested = True
            user.deletion_requested_at = datetime.now(timezone.utc)

            self.database.execute(
                update(UserSession)
                .where(
                    UserSession.user_id == user_id,
                    UserSession.revoked.is_(False),
                )
                .values(revoked=True)
            )

            self.database.commit()
            self.database.refresh(user)
            return True

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to request account deletion and revoke sessions"
            ) from exc
