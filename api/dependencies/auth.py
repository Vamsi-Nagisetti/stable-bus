
from fastapi import Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
import jwt

from core.database import get_db
from Repositories.UserRepository import UserRepository
from Repositories.SessionRepository import SessionRepository
from Management.UserManagement import UserManagement
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


def get_user_management(
    request: Request,
    db: Session = Depends(get_db),
) -> UserManagement:

    # Request-scoped repositories.
    user_repository = UserRepository(db)
    session_repository = SessionRepository(db)

    # Reuse application-level OTP management.
    otp_management = request.app.state.auth_orchestrator.otp_management

    # Reuse application-level SessionManagement.
    session_management = request.app.state.session_management

    return UserManagement(
        user_repository=user_repository,
        otp_management=otp_management,
        session_management=session_management,
        session_repository=session_repository,
    )


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    # 1. Ensure Authorization header contains a Bearer token.
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = credentials.credentials

    try:
        # 2. Validate JWT signature, expiry, issuer and audience.
        session_management = request.app.state.session_management
        claims = session_management.verify_access_token(access_token)

        # 3. Extract user ID from JWT subject.
        user_id = int(claims["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Fetch user from PostgreSQL.
    user_repository = UserRepository(db)
    user = user_repository.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # 5. Reject accounts with pending deletion requests.
    if getattr(user, "is_deletion_requested", False) is True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deletion requested. Account access is restricted.",
        )

    return user
