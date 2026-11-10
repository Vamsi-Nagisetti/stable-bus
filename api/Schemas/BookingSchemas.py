
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BookingPassengerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passenger_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, min_length=1, max_length=20)
    seat_key: str = Field(..., min_length=1)
    title: str | None = None
    dob: date | None = None

    @model_validator(mode="after")
    def validate_passenger(self):
        if self.passenger_id:
            if any(value is not None for value in (
                self.name, self.age, self.gender
            )):
                raise ValueError(
                    "Provide passenger_id OR passenger details, not both"
                )
        elif not all(value is not None for value in (
            self.name, self.age, self.gender
        )):
            raise ValueError(
                "Name, age and gender are required for a new passenger"
            )

        return self


class CreateBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(
        default=None,
        min_length=16,
        max_length=100,
    )

    # Required for guest checkout; optional for logged-in users.
    customer_mobile: str | None = Field(
        default=None,
        min_length=10,
        max_length=15,
    )
    passenger_email: str | None = Field(
        default=None,
        max_length=254,
    )

    source_city_id: str
    destination_city_id: str
    journey_date: date
    bus_id: str
    search_key: str
    boarding_id: str
    dropping_id: str

    passengers: list[BookingPassengerRequest] = Field(
        ..., min_length=1
    )

    @model_validator(mode="after")
    def validate_unique_seats(self):
        seat_keys = [p.seat_key for p in self.passengers]

        if len(seat_keys) != len(set(seat_keys)):
            raise ValueError("Each passenger must have a unique seat")

        return self
