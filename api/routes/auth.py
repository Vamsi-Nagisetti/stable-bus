
import logging
from Management.OtpMangement import OTPDeliveryError
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from Management.RateLimitManagement import RateLimitExceededError
from core.request_context import request_id_context

from fastapi import Depends
from api.dependencies.auth import get_user_management

from api.Schemas.AuthSchemas import (
    SendOTPRequest,
    SendOTPResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    LogoutRequest, LogoutResponse
)
from Management.UserManagement import UserManagement

logger = logging.getLogger("stablebus.api.auth")

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)


@router.post(
    "/send-otp",
    response_model=SendOTPResponse,
    status_code=status.HTTP_200_OK
)
def send_otp(
    payload: SendOTPRequest,
    request: Request
):
    mobile_number = payload.mobile_number
    client_ip = request.client.host if request.client else "unknown"

    auth_orchestrator = request.app.state.auth_orchestrator

    try:
        auth_orchestrator.send_otp(
            mobile_number=mobile_number,
            client_ip=client_ip
        )

        return SendOTPResponse(
            success=True,
            message="OTP sent successfully",
            expires_in=60,
            request_id=request_id_context.get()
        )

    except RateLimitExceededError as exc:
        logger.warning(
            "OTP request rate limited | retry_after=%s",
            exc.retry_after
        )

        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "success": False,
                "message": str(exc),
                "retry_after": exc.retry_after,
                "request_id": request_id_context.get()
            },
            headers={"Retry-After": str(exc.retry_after)}
        )

    except OTPDeliveryError:
        logger.exception("OTP delivery failed")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "message": "Unable to send OTP. Please try again later.",
                "request_id": request_id_context.get()
            }
        )


@router.post(
    "/verify-otp",
    response_model=VerifyOTPResponse,
    status_code=200,
)
def verify_otp(
    payload: VerifyOTPRequest,
    user_management: UserManagement = Depends(get_user_management),
):
    try:
        result = user_management.verify_otp_and_login(
            mobile_number=payload.mobile_number,
            otp=payload.otp,
        )

        return VerifyOTPResponse(
            success=True,
            message="Login successful",
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
        )

    except ValueError as exc:
        logger.warning(
            "OTP verification or account validation failed | reason=%s",
            str(exc),
        )
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "message": str(exc),
                "request_id": request_id_context.get(),
            },
        )


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
)
def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    user_management: UserManagement = Depends(get_user_management),
):
    try:
        tokens = user_management.refresh_user_session(
            refresh_token=payload.refresh_token,
        )

        logger.info("Refresh token API completed successfully")

        return {
            "success": True,
            "message": "Token refreshed successfully",
            **tokens,
        }

    except ValueError as exc:
        logger.warning(
            "Refresh token request rejected | reason=%s",
            str(exc),
        )

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": str(exc),
                "request_id": request_id_context.get(),
            },
        )


@router.post(
    "/logout",
    response_model=LogoutResponse,
)
def logout(
    payload: LogoutRequest,
    user_management: UserManagement = Depends(get_user_management),
):
    user_management.user_logout(
        refresh_token=payload.refresh_token,
    )

    logger.info("Logout API completed successfully")

    return {
        "success": True,
        "message": "Logged out successfully",
    }
