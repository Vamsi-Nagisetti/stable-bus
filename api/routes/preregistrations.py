
import time

from fastapi import APIRouter, Depends, HTTPException, status
from prometheus_client import Counter, Histogram
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.Schemas.PreRegistrationSchemas import CreatePreRegistrationRequest
from core.database import get_db
from models.PreRegisteredUser import PreRegisteredUser

router = APIRouter(prefix="/api/v1/preregistrations", tags=["Pre-Registrations"])

PREREGISTRATION_REQUESTS = Counter(
    "stablebus_preregistration_requests_total",
    "Total preregistration requests",
    ["outcome"],
)

PREREGISTRATION_DURATION = Histogram(
    "stablebus_preregistration_request_duration_seconds",
    "Preregistration request processing duration",
)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_pre_registration(
    payload: CreatePreRegistrationRequest,
    db: Session = Depends(get_db),
):
    start_time = time.perf_counter()
    outcome = "server_error"

    try:
        record = PreRegisteredUser(
            name=payload.name,
            mobile=payload.mobile,
            email=payload.email,
            city=payload.city,
        )
        db.add(record)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            outcome = "duplicate"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This mobile number or email is already registered",
            )

        db.refresh(record)
        outcome = "success"

        return {
            "id": record.id,
            "name": record.name,
            "mobile": record.mobile,
            "email": record.email,
            "city": record.city,
            "created_at": record.created_at.isoformat(),
        }

    finally:
        PREREGISTRATION_REQUESTS.labels(outcome=outcome).inc()
        PREREGISTRATION_DURATION.observe(time.perf_counter() - start_time)
