
from datetime import datetime, timezone , timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from models.UserSession import UserSession


class SessionRepository:

    def __init__(self, database):
        self.database = database

    def create(self, user_session: UserSession) -> UserSession:
        try:
            self.database.add(user_session)
            self.database.commit()
            self.database.refresh(user_session)
            return user_session

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to create user session"
            ) from exc

    def get_by_refresh_token_hash(
        self, token_hash: str
    ) -> UserSession | None:
        try:
            statement = select(UserSession).where(
                UserSession.refresh_token_hash == token_hash
            )
            result = self.database.execute(statement)
            return result.scalar_one_or_none()

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to retrieve user session"
            ) from exc

    def revoke(self, session_id: int) -> bool:
        try:
            statement = (
                update(UserSession)
                .where(
                    UserSession.id == session_id,
                    UserSession.revoked.is_(False),
                )
                .values(revoked=True)
            )

            result = self.database.execute(statement)
            self.database.commit()
            return result.rowcount > 0

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to revoke user session"
            ) from exc
    
    def rotate_refresh_token(
        self,
        session_id: int,
        old_token_hash: str,
        new_token_hash: str,
        inactivity_days: int = 30,
    ) -> bool:
        now = datetime.now(timezone.utc)
        new_expiry = now + timedelta(days=inactivity_days)

        try:
            statement = (
                update(UserSession)
                .where(
                    UserSession.id == session_id,
                    UserSession.refresh_token_hash == old_token_hash,
                    UserSession.revoked.is_(False),
                    UserSession.expires_at > now,
                )
                .values(
                    previous_refresh_token_hash=old_token_hash,
                    refresh_token_hash=new_token_hash,
                    last_refreshed_at=now,
                    expires_at=new_expiry,
                )
            )

            result = self.database.execute(statement)
            self.database.commit()

            return result.rowcount == 1

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to rotate refresh token"
            ) from exc

    def revoke_if_previous_token_matches(
        self,
        token_hash: str,
    ) -> bool:
        try:
            statement = (
                update(UserSession)
                .where(
                    UserSession.previous_refresh_token_hash == token_hash,
                    UserSession.revoked.is_(False),
                )
                .values(revoked=True)
            )

            result = self.database.execute(statement)
            self.database.commit()
            return result.rowcount > 0

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to revoke session after refresh-token reuse"
            ) from exc


    def refresh_session(self, refresh_token: str, session_repository) -> dict:
        if not refresh_token:
            raise ValueError("Refresh token is required")

        old_hash = self.hash_refresh_token(refresh_token)

        # Find the session associated with this token.
        session = session_repository.get_by_refresh_token_hash(old_hash)

        if session is None:
            # The token may have been used already.
            session_repository.revoke_if_previous_token_matches(old_hash)
            raise ValueError("Invalid refresh token")

        now = datetime.now(timezone.utc)

        # Protect against expired or revoked sessions.
        if session.revoked:
            raise ValueError("Refresh session has been revoked")

        if session.expires_at <= now:
            raise ValueError("Refresh session has expired")

        # Generate the replacement refresh token.
        new_refresh_token = self.generate_refresh_token()
        new_hash = self.hash_refresh_token(new_refresh_token)

        # Atomically replace the old token.
        rotated = session_repository.rotate_refresh_token(
            session_id=session.id,
            old_token_hash=old_hash,
            new_token_hash=new_hash,
            inactivity_days=30,
        )

        if not rotated:
            # Another request may have rotated this token first.
            session_repository.revoke_if_previous_token_matches(old_hash)
            raise ValueError("Refresh token is no longer valid")

        # Issue a new access token for the same user.
        new_access_token = self.create_access_token(session.user_id)

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
        }


    def revoke_all_for_user(self, user_id: int) -> int:
        try:
            statement = update(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked.is_(False),
            ).values(revoked=True)

            result = self.database.execute(statement)
            self.database.commit()

            return result.rowcount or 0

        except SQLAlchemyError as exc:
            self.database.rollback()
            raise RuntimeError(
                "Unable to revoke user sessions"
            ) from exc
