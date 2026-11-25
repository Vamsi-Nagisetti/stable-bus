from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.dependencies.auth import get_optional_current_user
from api.Schemas.ReviewSchemas import CreateReviewRequest
from core.database import get_db
from models.Booking import Booking
from models.Review import Review
from Orchestrators.booking_orchestrator import BookingOrchestrator
from core.constants.booking_status import BookingStatus

router = APIRouter(prefix="/api/v1/reviews", tags=["Reviews & Ratings"])


@router.post("/bookings/{booking_id}", status_code=status.HTTP_201_CREATED)
def create_booking_review(
    booking_id: str,
    payload: CreateReviewRequest,
    current_user=Depends(get_optional_current_user),
    guest_access_token: str | None = Header(default=None, alias="X-Guest-Access-Token"),
    db: Session = Depends(get_db),
):
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if not BookingOrchestrator.authorize_booking(
        booking=booking,
        user_id=str(current_user.id) if current_user else None,
        guest_access_token=guest_access_token,
    ):
        raise HTTPException(status_code=404, detail="Booking not found")

    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail="Only confirmed trips can be reviewed")
    if booking.journey_date >= today_ist:
        raise HTTPException(status_code=409, detail="You can review this trip after its journey date")

    review = Review(
        booking_id=booking.id,
        user_id=str(current_user.id) if current_user else None,
        bus_id=booking.bus_id,
        rating=payload.rating,
        comment=payload.comment.strip() if payload.comment else None,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A review has already been submitted for this booking")

    db.refresh(review)
    return {
        "review_id": review.id,
        "booking_id": review.booking_id,
        "bus_id": review.bus_id,
        "rating": review.rating,
        "comment": review.comment,
        "created_at": review.created_at.isoformat(),
    }


@router.get("/buses/{bus_id}")
def get_bus_reviews(bus_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Review).where(Review.bus_id == bus_id).order_by(Review.created_at.desc()).limit(100)
    ).all()
    average, count = db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(Review.bus_id == bus_id)
    ).one()
    return {
        "bus_id": bus_id,
        "average_rating": round(float(average), 2) if average is not None else None,
        "review_count": int(count or 0),
        "reviews": [
            {"review_id": r.id, "rating": r.rating, "comment": r.comment, "created_at": r.created_at.isoformat()}
            for r in rows
        ],
    }
