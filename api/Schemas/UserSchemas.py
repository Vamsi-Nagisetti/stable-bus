
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class UserProfileResponse(BaseModel):
    id: int
    mobile_number: str


class ContactDetailsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        pattern=r"^[6-9]\d{9}$",
    )
    email: str = Field(
        ...,
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )


class ContactDetailsResponse(BaseModel):
    mobile_number: str
    email: str


class SavedPassengerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Literal["Mr", "Ms", "Mrs", "Master"] | None = None
    name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: str | None = Field(default=None, max_length=10)
    age: int = Field(..., ge=1, le=120)
    gender: str = Field(..., min_length=1, max_length=20)

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value):
        if value is None or not value.strip():
            return None

        try:
            datetime.strptime(value, "%d/%m/%Y")
        except ValueError:
            raise ValueError("Date of birth must be a valid date in DD/MM/YYYY format")

        return value


class SavedPassengerUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Literal["Mr", "Ms", "Mrs", "Master"] | None = None
    name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: str | None = Field(default=None, max_length=10)
    age: int = Field(..., ge=1, le=120)
    gender: str = Field(..., min_length=1, max_length=20)

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value):
        if value is None or not value.strip():
            return None

        try:
            datetime.strptime(value, "%d/%m/%Y")
        except ValueError:
            raise ValueError("Date of birth must be a valid date in DD/MM/YYYY format")

        return value
