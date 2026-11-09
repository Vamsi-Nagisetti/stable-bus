import logging

from fastapi import APIRouter, HTTPException, Request, status

from Services.Bus.bus_service import BusService
from api.Schemas.BusSchemas import BusCityListResponse, BusSearchRequest, BusSeatMapRequest


logger = logging.getLogger("stablebus.api.buses")


router = APIRouter(
    prefix="/api/v1/buses",
    tags=["Buses"],
)


def get_bus_service(request: Request) -> BusService:
    bus_service = getattr(request.app.state, "bus_service", None)

    if bus_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bus service is currently unavailable",
        )

    return bus_service


@router.get(
    "/cities",
    response_model=BusCityListResponse,
)
def get_cities(request: Request):

    bus_service = get_bus_service(request)

    try:
        return bus_service.get_cities()

    except (ValueError, RuntimeError):
        logger.exception("Failed to fetch bus cities")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch cities from bus provider",
        )


@router.post("/search")
def search_buses(
    request: Request,
    search_request: BusSearchRequest,
):

    bus_service = get_bus_service(request)

    try:
        return bus_service.search_buses(
            from_city=search_request.from_city,
            to_city=search_request.to_city,
            travel_date=search_request.travel_date,
        )

    except (ValueError, RuntimeError):
        logger.exception("Failed to search buses")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to search buses from bus provider",
        )

@router.post("/seat-map")
def get_bus_seat_map(
    request: Request,
    seat_map_request: BusSeatMapRequest,
):
    bus_service = get_bus_service(request)

    try:
        return bus_service.get_seat_map(
            bus_key=seat_map_request.bus_key,
            search_key=seat_map_request.search_key,
            boarding_id=seat_map_request.boarding_id,
            dropping_id=seat_map_request.dropping_id,
        )

    except (ValueError, RuntimeError):
        logger.exception("Failed to fetch bus seat map")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch seat map from bus provider",
        )