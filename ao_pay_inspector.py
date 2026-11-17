
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from Adaptors.AOPayBusAPI.AOPayAdaptee import AOPayAdaptee
from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter


# Load environment variables
load_dotenv()

# Validate required configuration
required_env_vars = [
    "AOPAY_BASE_URL",
    "AOPAY_REGISTRATION_ID",
    "AOPAY_IP_ADDRESS",
    "AOPAY_IMEI_NUMBER",
]

missing_vars = [
    var for var in required_env_vars if not os.getenv(var)
]

if missing_vars:
    raise RuntimeError(
        f"Missing environment variables: {', '.join(missing_vars)}"
    )


# Initialize AO Pay adapter
adaptee = AOPayAdaptee(
    base_url=os.environ["AOPAY_BASE_URL"],
    timeout=30
)

adapter = AOPayAdapter(
    adaptee=adaptee,
    registration_id=os.environ["AOPAY_REGISTRATION_ID"],
    ip_address=os.environ["AOPAY_IP_ADDRESS"],
    imei_number=os.environ["AOPAY_IMEI_NUMBER"],
)


# Initialize FastAPI
app = FastAPI(
    title="StableBus - AO Pay API Inspector",
    description="Standalone API inspector for testing AO Pay bus APIs",
    version="1.0.0",
)


# Request models
class BusSearchRequest(BaseModel):
    from_city: str
    to_city: str
    travel_date: str


class BusSeatMapRequest(BaseModel):
    bus_key: str
    search_key: str
    boarding_id: str
    dropping_id: str


# Health check
@app.get("/")
def health_check():
    return {
        "service": "StableBus AO Pay Inspector",
        "status": "running"
    }


# 1. Bus City List
@app.get("/api/cities")
def get_cities():
    try:
        return adapter.BusCityList()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# 2. Bus Search
@app.post("/api/buses")
def get_buses(request: BusSearchRequest):
    try:
        return adapter.BusSearch(
            from_city=request.from_city,
            to_city=request.to_city,
            travel_date=request.travel_date
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# 3. Bus Seat Map
@app.post("/api/seats")
def get_seat_map(request: BusSeatMapRequest):
    try:
        return adapter.BusSeatMap(
            bus_key=request.bus_key,
            search_key=request.search_key,
            boarding_id=request.boarding_id,
            dropping_id=request.dropping_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
