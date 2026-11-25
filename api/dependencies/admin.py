import hmac
import os

from fastapi import Header, HTTPException, status


def require_admin(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """Protects admin endpoints with a shared secret (env ADMIN_API_KEY).

    Disabled (503) when ADMIN_API_KEY is not configured, so admin endpoints
    are never accidentally open.
    """
    expected = os.getenv("ADMIN_API_KEY", "")
    if len(expected) < 16:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured",
        )
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
        )
