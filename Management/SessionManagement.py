
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import hashlib
import secrets
import jwt
from dotenv import load_dotenv
from models.UserSession import UserSession

load_dotenv()


class SessionManagement:
    def __init__(self):
        private_key_path = Path(os.environ["JWT_PRIVATE_KEY_PATH"])
        public_key_path = Path(os.environ["JWT_PUBLIC_KEY_PATH"])

        self.private_key = private_key_path.read_text(encoding="utf-8")
        self.public_key = public_key_path.read_text(encoding="utf-8")

        self.issuer = os.getenv("JWT_ISSUER", "stablebus")
        self.audience = os.getenv("JWT_AUDIENCE", "stablebus-api")
        self.access_token_minutes = int(
            os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30")
        )

    def create_access_token(self, user_id: int) -> str:
        now = datetime.now(timezone.utc)

        payload = {
            "sub": str(user_id),
            "iss": self.issuer,
            "aud": self.audience,
            "iat": now,
            "exp": now + timedelta(minutes=self.access_token_minutes),
            "jti": str(uuid4()),
        }

        return jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
        )

    def verify_access_token(self, token: str) -> dict:
        return jwt.decode(
            token,
            self.public_key,
            algorithms=["RS256"],
            issuer=self.issuer,
            audience=self.audience,
            options={"require": ["sub", "iss", "aud", "iat", "exp", "jti"]},
        )

    def generate_refresh_token(self) -> str:
        """Generate a cryptographically random refresh token."""
        return secrets.token_urlsafe(32)


    def hash_refresh_token(self, refresh_token: str) -> str:
        """Return the SHA-256 hash of a refresh token."""
        return hashlib.sha256(
            refresh_token.encode("utf-8")
        ).hexdigest()

    def create_refresh_session(
        self,
        user_id: int,
        session_repository,
    ) -> str:
        now = datetime.now(timezone.utc)

        refresh_token = self.generate_refresh_token()
        refresh_token_hash = self.hash_refresh_token(refresh_token)

        user_session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            created_at=now,
            last_refreshed_at=now,
            expires_at=now + timedelta(days=30),
            revoked=False,
        )

        session_repository.create(user_session)

        # Return the raw token only to the caller.
        # The database stores its hash, not this value.
        return refresh_token


    def refresh_session(self, refresh_token: str, session_repository) -> dict:
        if not refresh_token:
            raise ValueError("Refresh token is required")

        old_hash = self.hash_refresh_token(refresh_token)

        session = session_repository.get_by_refresh_token_hash(old_hash)

        if session is None:
            session_repository.revoke_if_previous_token_matches(old_hash)
            raise ValueError("Invalid refresh token")

        now = datetime.now(timezone.utc)

        if session.revoked:
            raise ValueError("Refresh session has been revoked")

        if session.expires_at <= now:
            raise ValueError("Refresh session has expired")

        new_refresh_token = self.generate_refresh_token()
        new_hash = self.hash_refresh_token(new_refresh_token)

        rotated = session_repository.rotate_refresh_token(
            session_id=session.id,
            old_token_hash=old_hash,
            new_token_hash=new_hash,
            inactivity_days=30,
        )

        if not rotated:
            session_repository.revoke_if_previous_token_matches(old_hash)
            raise ValueError("Refresh token is no longer valid")

        new_access_token = self.create_access_token(session.user_id)

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
        }


    def logout(self, refresh_token: str, session_repository) -> bool:
        if not refresh_token:
            raise ValueError("Refresh token is required")

        token_hash = self.hash_refresh_token(refresh_token)

        session = session_repository.get_by_refresh_token_hash(
            token_hash
        )

        if session is None:
            return False

        if session.revoked:
            return False

        return session_repository.revoke(session.id)

