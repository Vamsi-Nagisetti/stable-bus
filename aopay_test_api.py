"""
StableBus - AO Pay local API test harness

Run from the StableBus project root so the existing Adaptors package is importable:
    uvicorn aopay_test_api:app --reload --host 127.0.0.1 --port 8000

Expected existing modules:
    Adaptors/AOPayBusAPI/AOPayAdaptee.py
    Adaptors/AOPayBusAPI/AOPayAdapter.py

Required .env variables:
    AOPAY_BASE_URL=https://travel.bospay.co.in
    AOPAY_REGISTRATION_ID=...
    AOPAY_IP_ADDRESS=...
    AOPAY_IMEI_NUMBER=...

This harness calls the existing adapter/adaptee. It does not implement booking or payment.
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from Adaptors.AOPayBusAPI.AOPayAdaptee import AOPayAdaptee
from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("stablebus.aopay.test")

REQUIRED_ENV = (
    "AOPAY_BASE_URL",
    "AOPAY_REGISTRATION_ID",
    "AOPAY_IP_ADDRESS",
    "AOPAY_IMEI_NUMBER",
)
missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
if missing:
    raise RuntimeError(
        "Missing environment variables: " + ", ".join(missing)
        + ". Add them to your project .env file."
    )

adaptee = AOPayAdaptee(
    base_url=os.environ["AOPAY_BASE_URL"],
    timeout=45,
)
adapter = AOPayAdapter(
    adaptee=adaptee,
    registration_id=os.environ["AOPAY_REGISTRATION_ID"],
    ip_address=os.environ["AOPAY_IP_ADDRESS"],
    imei_number=os.environ["AOPAY_IMEI_NUMBER"],
)

app = FastAPI(
    title="StableBus - AO Pay Test API",
    description="Local test-only proxy for city search, bus search and seat map.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local test harness only. Restrict this in production.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BusSearchRequest(BaseModel):
    from_city: str = Field(..., min_length=1)
    to_city: str = Field(..., min_length=1)
    travel_date: str = Field(..., description="AO Pay format: MM/DD/YYYY")


class SeatMapRequest(BaseModel):
    bus_key: str = Field(..., min_length=1)
    search_key: str = Field(..., min_length=1)
    boarding_id: str = Field(..., min_length=1)
    dropping_id: str = Field(..., min_length=1)


def _log_response_summary(label: str, data: Any) -> None:
    """Log useful response metadata without dumping opaque provider tokens."""
    if isinstance(data, dict):
        header = data.get("response_Header") or data.get("response_Header")
        if not header and isinstance(data.get("response"), dict):
            header = data["response"].get("response_Header")
        if isinstance(header, dict):
            logger.info(
                "%s response header: error_Code=%s error_Desc=%s status_Id=%s",
                label,
                header.get("error_Code"),
                header.get("error_Desc"),
                header.get("status_Id"),
            )
        buses = data.get("buses")
        if isinstance(buses, list):
            logger.info("%s returned %s buses", label, len(buses))
        seats = data.get("seatMap")
        if isinstance(seats, list):
            logger.info("%s returned %s seat records", label, len(seats))


@app.get("/")
def health():
    return {
        "service": "StableBus AO Pay test API",
        "status": "running",
        "docs": "/docs",
        "routes": ["/api/cities", "/api/buses", "/api/seats"],
    }


@app.get("/api/cities")
def get_cities():
    logger.info("Selection: user requested city list")
    try:
        result = adapter.BusCityList()
        _log_response_summary("BusCityList", result)
        return result
    except Exception as exc:
        logger.exception("BusCityList failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/buses")
def search_buses(request: BusSearchRequest):
    # Do not log full provider response or opaque bus/search keys.
    logger.info(
        "Selection: BusSearch from_city=%s to_city=%s travel_date=%s",
        request.from_city,
        request.to_city,
        request.travel_date,
    )
    try:
        result = adapter.BusSearch(
            request.from_city,
            request.to_city,
            request.travel_date,
        )
        _log_response_summary("BusSearch", result)
        return result
    except Exception as exc:
        logger.exception("BusSearch failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/seats")
def get_seat_map(request: SeatMapRequest):
    # IDs/keys are sent to the provider but deliberately not written to logs.
    logger.info(
        "Selection: BusSeatMap requested (bus/search/boarding/drop identifiers received)"
    )
    try:
        result = adapter.BusSeatMap(
            request.bus_key,
            request.search_key,
            request.boarding_id,
            request.dropping_id,
        )
        _log_response_summary("BusSeatMap", result)
        return result
    except Exception as exc:
        logger.exception("BusSeatMap failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
