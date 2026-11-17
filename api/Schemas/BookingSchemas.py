
from datetime import date, datetime

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
    boarding_point: dict | None = None
    dropping_point: dict | None = None

    passengers: list[BookingPassengerRequest] = Field(
        ..., min_length=1
    )

    @model_validator(mode="after")
    def validate_unique_seats(self):
        seat_keys = [p.seat_key for p in self.passengers]

        if len(seat_keys) != len(set(seat_keys)):
            raise ValueError("Each passenger must have a unique seat")

        return self


class CancellationChargesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seat_numbers: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def unique_seats(self):
        if len(self.seat_numbers) != len(set(self.seat_numbers)):
            raise ValueError("Seat numbers must be unique")
        return self


class CancellationRequest(CancellationChargesRequest):
    cancellation_charge_key: str = Field(..., min_length=1, max_length=2048)


class ProviderBookingHistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fromdate: str
    month: str = Field(..., min_length=2, max_length=2, pattern=r"^\d{2}$")
    todate: str
    type: int = Field(default=0, ge=0, le=1)
    year: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")

    @model_validator(mode="after")
    def validate_provider_dates(self):
        try:
            start = datetime.strptime(self.fromdate, "%m/%d/%Y").date()
            end = datetime.strptime(self.todate, "%m/%d/%Y").date()
        except ValueError as exc:
            raise ValueError("fromdate and todate must use MM/DD/YYYY") from exc
        if end < start:
            raise ValueError("todate must be on or after fromdate")
        if self.month != f"{start.month:02d}" or self.year != f"{start.year:04d}":
            raise ValueError("month and year must match fromdate")
        return self
