
import secrets

from core.database import SessionLocal
from models.User import User
from models.UserSession import UserSession
from Repositories.SessionRepository import SessionRepository
from Management.SessionManagement import SessionManagement


def test_logout_session_against_postgresql():
    db = SessionLocal()
    user = None

    try:
        # 1. Create a temporary test user.
        mobile_number = "9" + str(secrets.randbelow(10**9)).zfill(9)

        user = User(mobile_number=mobile_number)
        db.add(user)
        db.commit()
        db.refresh(user)

        # 2. Create the actual repository and session manager.
        repository = SessionRepository(db)
        manager = SessionManagement()

        # 3. Create a refresh session.
        refresh_token = manager.create_refresh_session(
            user_id=user.id,
            session_repository=repository,
        )

        # 4. Logout using the actual refresh token.
        logout_result = manager.logout(
            refresh_token=refresh_token,
            session_repository=repository,
        )

        assert logout_result is True

        # 5. Verify that PostgreSQL marks the session as revoked.
        db.expire_all()

        stored_session = (
            db.query(UserSession)
            .filter(UserSession.user_id == user.id)
            .first()
        )

        assert stored_session is not None
        assert stored_session.revoked is True

        # 6. The same token must not be able to logout again.
        second_logout = manager.logout(
            refresh_token=refresh_token,
            session_repository=repository,
        )

        assert second_logout is False

        # 7. A revoked refresh token must not refresh the session.
        try:
            manager.refresh_session(
                refresh_token=refresh_token,
                session_repository=repository,
            )
            assert False, "A revoked refresh token was accepted"
        except ValueError:
            pass

    finally:
        # Clean up only this test user's records.
        if user is not None and user.id is not None:
            db.query(UserSession).filter(
                UserSession.user_id == user.id
            ).delete(synchronize_session=False)

            db.delete(user)
            db.commit()

        db.close()
