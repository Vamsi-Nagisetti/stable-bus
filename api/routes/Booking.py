
import logging
import os

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from api.dependencies.auth import (
    get_current_user,
    get_optional_current_user,
)
from api.Schemas.BookingSchemas import CreateBookingRequest

from Repositories.UserPassengerRepository import UserPassengerRepository
from Repositories.BookingRepository import BookingRepository
from Repositories.PaymentRepository import PaymentRepository
from Repositories.PaymentCacheRepository import PaymentCacheRepository
from Repositories.RefundRepository import RefundRepository

from Orchestrators.booking_orchestrator import (
    BookingOrchestrator,
    BookingOrchestrationError,
)

from Services.Payments.PaymentService import PaymentService


logger = logging.getLogger("stablebus.api.bookings")

router = APIRouter(
    prefix="/api/v1/bookings",
    tags=["Bookings"],
)


def get_booking_adapter(request: Request):
    adapter = getattr(request.app.state, "booking_adapter", None)

    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail="Booking provider is unavailable",
        )

    return adapter


def get_passenger_repository(request: Request):
    return UserPassengerRepository(request.app.state.dynamodb)


def get_payment_service(
    request: Request,
    db: Session = Depends(get_db),
):
    provider = getattr(request.app.state, "payment_provider", None)

    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="Payment provider is unavailable",
        )

    return PaymentService(
        payment_provider=provider,
        payment_repository=PaymentRepository(db),
        booking_repository=BookingRepository(db),
        payment_cache_repository=PaymentCacheRepository(
            request.app.state.cache
        ),
        refund_repository=RefundRepository(db),
        gateway_name=request.app.state.payment_gateway_name,
    )


def require_booking_access(
    booking_id: str,
    db: Session,
    current_user,
    guest_access_token: str | None,
):
    booking = BookingRepository(db).get_by_id(booking_id)

    if not BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id=str(current_user.id) if current_user else None,
        guest_access_token=guest_access_token,
    ):
        raise HTTPException(
            status_code=404,
            detail="Booking not found",
        )

    return booking


class SimulateMockPaymentRequest(BaseModel):
    payment_id: str

class InitiatePaymentRequest(BaseModel):
    idempotency_key: str = Field(
        ...,
        min_length=16,
        max_length=150,
    )


class VerifyPaymentRequest(BaseModel):
    payment_id: str
    gateway_payment_id: str
    signature: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_booking(
    booking_request: CreateBookingRequest,
    request: Request,
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
    passenger_repository=Depends(get_passenger_repository),
    adapter=Depends(get_booking_adapter),
):
    try:
        if not current_user and not booking_request.customer_mobile:
            raise HTTPException(
                status_code=400,
                detail="Mobile number is required for guest booking",
            )

        bus_provider = request.app.state.bus_service.bus_provider

        seat_map_response = bus_provider.BusSeatMap(
            bus_key=booking_request.bus_id,
            search_key=booking_request.search_key,
            boarding_id=booking_request.boarding_id,
            dropping_id=booking_request.dropping_id,
        )

        booking, guest_token = BookingOrchestrator.start_booking(
            db=db,
            user_id=str(current_user.id) if current_user else None,
            request=booking_request,
            passenger_repository=passenger_repository,
            adapter=adapter,
            seat_map_response=seat_map_response,
            customer_mobile=(
                current_user.mobile_number
                if current_user
                else booking_request.customer_mobile
            ),
            passenger_email=booking_request.passenger_email,
        )

        response = {
            "booking_id": booking.id,
            "booking_status": booking.status,
            "temporary_booking_reference": booking.temp_booking_ref,
            "seat_numbers": booking.seat_numbers,
            "total_amount": str(booking.total_amount),
            "currency": booking.currency,
        }

        if guest_token:
            response["guest_access_token"] = guest_token

        return response

    except HTTPException:
        db.rollback()
        raise

    except BookingOrchestrationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    except Exception:
        db.rollback()
        logger.exception("Failed to create booking")

        raise HTTPException(
            status_code=502,
            detail="Unable to create temporary booking",
        )


@router.post("/{booking_id}/payments")
def initiate_payment(
    booking_id: str,
    payment_request: InitiatePaymentRequest,
    current_user=Depends(get_optional_current_user),
    guest_access_token: str | None = Header(
        default=None,
        alias="X-Guest-Access-Token",
    ),
    db: Session = Depends(get_db),
    payment_service=Depends(get_payment_service),
):
    try:
        booking = require_booking_access(
            booking_id,
            db,
            current_user,
            guest_access_token,
        )

        customer = {
            "name": "StableBus Customer",
            "email": (
                booking.passenger_email
                or os.getenv("PAYMENT_CUSTOMER_EMAIL", "")
            ),
            "contact": (
                current_user.mobile_number
                if current_user
                else booking.customer_mobile
            ),
        }

        return BookingOrchestrator.initiate_booking_payment(
            db=db,
            booking_id=booking_id,
            user_id=str(current_user.id) if current_user else None,
            payment_service=payment_service,
            customer=customer,
            idempotency_key=payment_request.idempotency_key,
            guest_access_token=guest_access_token,
        )

    except BookingOrchestrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/{booking_id}/payments/mock-success")
def simulate_mock_payment(
    booking_id: str,
    payment_request: SimulateMockPaymentRequest,
    request: Request,
    current_user=Depends(get_optional_current_user),
    guest_access_token: str | None = Header(
        default=None,
        alias="X-Guest-Access-Token",
    ),
    db: Session = Depends(get_db),
):
    # Never allow mock payment simulation in production.
    if (
        os.getenv("APP_ENV", "development").lower() == "production"
        or getattr(request.app.state, "payment_gateway_name", "") != "MOCK"
    ):
        raise HTTPException(
            status_code=404,
            detail="Mock payment simulation is unavailable",
        )

    # Validate booking ownership / guest access.
    booking = require_booking_access(
        booking_id,
        db,
        current_user,
        guest_access_token,
    )

    # Validate that the payment belongs to this booking.
    payment = PaymentRepository(db).get_by_id(payment_request.payment_id)

    if payment is None or str(payment.booking_id) != str(booking.id):
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    if payment.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"Payment cannot be simulated in status: {payment.status}",
        )

    if not payment.gateway_order_id:
        raise HTTPException(
            status_code=400,
            detail="Gateway order ID is missing",
        )

    # Use the SAME adapter instance used by PaymentService.
    payment_provider = request.app.state.payment_provider

    try:
        gateway_payment_id = (
            payment_provider.simulate_successful_payment(
                payment.gateway_order_id
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    return {
        "payment_id": payment.id,
        "gateway_payment_id": gateway_payment_id,
        "status": "CAPTURED",
        "message": "Mock payment simulated successfully",
    }
    
@router.post("/{booking_id}/payments/verify")
def verify_payment(
    booking_id: str,
    payment_request: VerifyPaymentRequest,
    current_user=Depends(get_optional_current_user),
    guest_access_token: str | None = Header(
        default=None,
        alias="X-Guest-Access-Token",
    ),
    db: Session = Depends(get_db),
    payment_service=Depends(get_payment_service),
):
    try:
        return BookingOrchestrator.verify_booking_payment(
            db=db,
            booking_id=booking_id,
            user_id=str(current_user.id) if current_user else None,
            payment_service=payment_service,
            payment_id=payment_request.payment_id,
            gateway_payment_id=payment_request.gateway_payment_id,
            signature=payment_request.signature,
            guest_access_token=guest_access_token,
        )

    except BookingOrchestrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{booking_id}/ticketing")
def complete_ticketing(
    booking_id: str,
    current_user=Depends(get_optional_current_user),
    guest_access_token: str | None = Header(
        default=None,
        alias="X-Guest-Access-Token",
    ),
    db: Session = Depends(get_db),
    adapter=Depends(get_booking_adapter),
):
    try:
        return BookingOrchestrator.complete_ticketing(
            db=db,
            booking_id=booking_id,
            user_id=str(current_user.id) if current_user else None,
            adapter=adapter,
            guest_access_token=guest_access_token,
        )

    except BookingOrchestrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{booking_id}/requery")
def requery_booking(
    booking_id: str,
    current_user=Depends(get_optional_current_user),
    guest_access_token: str | None = Header(
        default=None,
        alias="X-Guest-Access-Token",
    ),
    db: Session = Depends(get_db),
    adapter=Depends(get_booking_adapter),
):
    try:
        return BookingOrchestrator.requery_ticketing(
            db=db,
            booking_id=booking_id,
            user_id=str(current_user.id) if current_user else None,
            adapter=adapter,
            guest_access_token=guest_access_token,
        )

    except BookingOrchestrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
