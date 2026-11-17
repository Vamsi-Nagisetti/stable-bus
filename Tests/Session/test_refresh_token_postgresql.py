
import secrets

from core.database import SessionLocal
from models.User import User
from models.UserSession import UserSession
from Repositories.SessionRepository import SessionRepository
from Management.SessionManagement import SessionManagement


def test_refresh_token_rotation_against_postgresql():
    db = SessionLocal()
    user = None

    try:
        # 1. Create a unique test user.
        mobile_number = "9" + str(secrets.randbelow(10**9)).zfill(9)

        user = User(mobile_number=mobile_number)
        db.add(user)
        db.commit()
        db.refresh(user)

        # 2. Create the actual repository and session manager.
        repository = SessionRepository(db)
        manager = SessionManagement()

        # 3. Create the initial refresh session.
        old_token = manager.create_refresh_session(
            user_id=user.id,
            session_repository=repository,
        )

        assert repository.get_by_refresh_token_hash(
            manager.hash_refresh_token(old_token)
        ) is not None

        # 4. Refresh using the original token.
        first_result = manager.refresh_session(
            refresh_token=old_token,
            session_repository=repository,
        )

        new_token = first_result["refresh_token"]

        assert first_result["access_token"]
        assert new_token != old_token

        # 5. Verify that the old token is no longer valid.
        assert repository.get_by_refresh_token_hash(
            manager.hash_refresh_token(old_token)
        ) is None

        # 6. Verify that the new token is stored.
        assert repository.get_by_refresh_token_hash(
            manager.hash_refresh_token(new_token)
        ) is not None

        # 7. Verify that the new token can refresh again.
        second_result = manager.refresh_session(
            refresh_token=new_token,
            session_repository=repository,
        )

        assert second_result["access_token"]
        assert second_result["refresh_token"] != new_token

    finally:
        # Remove only the test user's records.
        if user is not None and user.id is not None:
            db.query(UserSession).filter(
                UserSession.user_id == user.id
            ).delete(synchronize_session=False)

            db.delete(user)
            db.commit()

        db.close()
