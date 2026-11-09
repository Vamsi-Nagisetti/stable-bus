
import os
import hashlib
import secrets
import logging

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from dotenv import load_dotenv

from models.UserSession import UserSession


load_dotenv()

logger = logging.getLogger("stablebus.management.session")


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

        self.refresh_token_days = 90

    # --------------------------------------------------
    # ACCESS TOKEN MANAGEMENT
    # --------------------------------------------------

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
            options={
                "require": [
                    "sub",
                    "iss",
                    "aud",
                    "iat",
                    "exp",
                    "jti",
                ]
            },
        )

    # --------------------------------------------------
    # REFRESH TOKEN GENERATION AND HASHING
    # --------------------------------------------------

    def generate_refresh_token(self) -> str:

        return secrets.token_urlsafe(32)

    def hash_refresh_token(self, refresh_token: str) -> str:

        return hashlib.sha256(
            refresh_token.encode("utf-8")
        ).hexdigest()

    # --------------------------------------------------
    # CREATE REFRESH SESSION
    # --------------------------------------------------

    def create_refresh_session(
        self,
        user_id: int,
        session_repository,
    ) -> str:

        now = datetime.now(timezone.utc)

        refresh_token = self.generate_refresh_token()

        refresh_token_hash = self.hash_refresh_token(
            refresh_token
        )

        user_session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            created_at=now,
            last_refreshed_at=now,
            expires_at=now + timedelta(days=self.refresh_token_days),
            revoked=False,
        )

        session_repository.create(user_session)

        logger.info(
            "Refresh session created successfully | user_id=%s",
            user_id,
        )

        # Return raw token only to the caller.
        # Database stores only its SHA-256 hash.
        return refresh_token

    # --------------------------------------------------
    # REFRESH SESSION
    # --------------------------------------------------

    def refresh_session(
        self,
        refresh_token: str,
        session_repository,
    ) -> dict:

        if not refresh_token:
            raise ValueError("Refresh token is required")

        old_hash = self.hash_refresh_token(refresh_token)

        # Find session using the current token hash.
        session = session_repository.get_by_refresh_token_hash(
            old_hash
        )

        if session is None:

            # This token may be expired, invalid, or previously rotated.
            # Do not automatically revoke the session here.
            #
            # A concurrent legitimate refresh request may also reach
            # this condition after another request has rotated the token.

            logger.warning(
                "Refresh attempted with an invalid or previously rotated token"
            )

            raise ValueError("Invalid refresh token")

        now = datetime.now(timezone.utc)

        # Check whether session is revoked.
        if session.revoked:

            raise ValueError("Refresh session has been revoked")

        # Check session expiry.
        expires_at = session.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= now:

            raise ValueError("Refresh session has expired")

        # Generate replacement refresh token.
        new_refresh_token = self.generate_refresh_token()

        new_hash = self.hash_refresh_token(
            new_refresh_token
        )

        # Atomically rotate the refresh token.
        rotated = session_repository.rotate_refresh_token(
            session_id=session.id,
            old_token_hash=old_hash,
            new_token_hash=new_hash,
            inactivity_days=self.refresh_token_days,
        )

        if not rotated:

            # Another request may have rotated the token first.
            # Reject this request without revoking the session.

            logger.warning(
                "Concurrent or stale refresh-token rotation rejected | session_id=%s",
                session.id,
            )

            raise ValueError("Refresh token is no longer valid")

        # Issue a new access token only after successful rotation.
        new_access_token = self.create_access_token(
            session.user_id
        )

        logger.info(
            "Refresh token rotated successfully | user_id=%s | session_id=%s",
            session.user_id,
            session.id,
        )

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
        }

    # --------------------------------------------------
    # LOGOUT
    # --------------------------------------------------

    def logout(
        self,
        refresh_token: str,
        session_repository,
    ) -> bool:

        if not refresh_token:
            raise ValueError("Refresh token is required")

        token_hash = self.hash_refresh_token(
            refresh_token
        )

        session = session_repository.get_by_refresh_token_hash(
            token_hash
        )

        if session is None:
            return False

        if session.revoked:
            return False

        revoked = session_repository.revoke(
            session.id
        )

        if revoked:

            logger.info(
                "User session revoked successfully | user_id=%s | session_id=%s",
                session.user_id,
                session.id,
            )

        return revoked
