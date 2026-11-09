
from pydantic import BaseModel, Field, ConfigDict


class SendOTPRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mobile_number: str = Field(
        ...,
        pattern=r"^[6-9]\d{9}$",
        description="Valid 10-digit Indian mobile number",
    )


class SendOTPResponse(BaseModel):
    success: bool
    message: str
    expires_in: int
    request_id: str


class VerifyOTPRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mobile_number: str = Field(
        ...,
        pattern=r"^[6-9]\d{9}$",
        description="Valid 10-digit Indian mobile number",
    )

    otp: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="Six-digit OTP",
    )


class VerifyOTPResponse(BaseModel):
    success: bool
    message: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(
        ...,
        min_length=1,
        description="Current refresh token",
    )


class RefreshTokenResponse(BaseModel):
    success: bool
    message: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"



class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(
        ...,
        min_length=1,
        description="Current refresh token",
    )


class LogoutResponse(BaseModel):
    success: bool
    message: str
