from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BusCityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cities: list[dict[str, Any]]
    total: int


class BusSearchRequest(BaseModel):
    from_city: str = Field(..., min_length=1)
    to_city: str = Field(..., min_length=1)
    travel_date: str = Field(
        ...,
        description="Travel date in MM/DD/YYYY format",
    )

    @field_validator("from_city", "to_city")
    @classmethod
    def validate_city_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("City ID cannot be empty")

        return value

    @field_validator("travel_date")
    @classmethod
    def validate_travel_date(cls, value: str) -> str:
        try:
            parsed_date = datetime.strptime(value, "%m/%d/%Y")
        except ValueError:
            raise ValueError("Travel date must be in MM/DD/YYYY format")

        return parsed_date.strftime("%m/%d/%Y")

    @model_validator(mode="after")
    def validate_route(self):
        if self.from_city == self.to_city:
            raise ValueError("Origin and destination cities must be different")

        return self


class BusSeatMapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bus_key: str = Field(..., min_length=1)
    search_key: str = Field(..., min_length=1)
    boarding_id: str = Field(..., min_length=1)
    dropping_id: str = Field(..., min_length=1)
