import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreatePreRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=100)
    mobile: str = Field(..., min_length=10, max_length=10)
    email: str = Field(..., min_length=5, max_length=254)
    city: str | None = Field(default=None, max_length=100)

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[6-9]\d{9}", value):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return value

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("name", "city")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None
