import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies.admin import require_admin
from api.dependencies.auth import get_current_user, get_optional_current_user
from api.Schemas.ReviewSchemas import (
    CreateReviewRequest,
    ReviewStatusRequest,
    RewardUpdateRequest,
)
from core.constants.booking_status import BookingStatus
from core.database import get_db
from models.Booking import Booking
from Orchestrators.booking_orchestrator import BookingOrchestrator
from Repositories.ReviewRepository import (
    AlreadyReviewed,
    ReviewRepository,
    get_review_repository,
    operator_key,
)
from Services.Wallet.WalletService import WalletService

logger = logging.getLogger("stablebus.api.reviews")

def _minutes(value) -> int | None:
    match = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", str(value or ""), re.IGNORECASE)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    meridiem = (match.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return hour * 60 + minute if hour < 24 and minute < 60 else None


def _trip_has_arrived(booking: Booking) -> bool:
    """True once the bus has reached its destination (India time). An overnight trip
    arrives the next day. Without readable times, the journey day must be over."""
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    point = booking.boarding_point if isinstance(booking.boarding_point, dict) else {}
    bus = point.get("_bus") if isinstance(point.get("_bus"), dict) else {}
    departs = _minutes(bus.get("departure_time") or point.get("boarding_Time") or point.get("boarding_time"))
    arrives = _minutes(bus.get("arrival_time"))
    if arrives is not None:
        day = datetime(
            booking.journey_date.year, booking.journey_date.month, booking.journey_date.day,
            tzinfo=ZoneInfo("Asia/Kolkata"),
        )
        if departs is not None and arrives <= departs:
            day += timedelta(days=1)
        return now >= day + timedelta(minutes=arrives)
    return booking.journey_date < now.date()


router = APIRouter(prefix="/api/v1/reviews", tags=["Reviews & Ratings"])


def _repository(request: Request) -> ReviewRepository:
    repository = get_review_repository(request.app)
    if repository is None:
        raise HTTPException(status_code=503, detail="Ratings are currently unavailable")
    return repository


def _award(db: Session, repository: ReviewRepository, user_id: str | None, booking_id: str, review: dict) -> int:
    """Give the review coins once. Safe to call again (idempotent)."""
    if not user_id or review.get("coins_awarded"):
        return int(review.get("coins_awarded") or 0)
    coins = repository.get_reward_coins()
    if coins <= 0:
        return 0
    try:
        WalletService(db).credit_review_reward(user_id, booking_id, coins)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Review reward failed for booking %s", booking_id)
        return 0
    # The lot exists now (new or earlier), remember it so the app shows it as given.
    try:
        repository.mark_reward(booking_id, coins)
    except Exception:
        logger.exception("Could not mark review reward for booking %s", booking_id)
    return coins


@router.post("/bookings/{booking_id}", status_code=status.HTTP_201_CREATED)
def create_booking_review(
    booking_id: str,
    payload: CreateReviewRequest,
    request: Request,
    current_user=Depends(get_optional_current_user),
    guest_access_token: str | None = Header(default=None, alias="X-Guest-Access-Token"),
    db: Session = Depends(get_db),
):
    repository = _repository(request)

    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    user_id = str(current_user.id) if current_user else None
    if not BookingOrchestrator.authorize_booking(
        booking=booking, user_id=user_id, guest_access_token=guest_access_token
    ):
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail="Only confirmed trips can be rated")
    if not _trip_has_arrived(booking):
        raise HTTPException(status_code=409, detail="You can rate this trip after your journey")

    comment = payload.comment.strip() if payload.comment else None
    operator_name = (booking.operator_name or "").strip() or "Bus operator"
    key = operator_key(booking.operator_name, fallback=booking.bus_id)

    try:
        review = repository.create_review(
            booking_id=booking.id,
            user_id=user_id,
            operator_name=operator_name,
            op_key=key,
            rating=payload.rating,
            comment=comment,
            tags=payload.tags,
        )
    except AlreadyReviewed:
        existing = repository.get_review(booking.id)
        # Heal a half-finished earlier attempt (review saved, coins not yet given).
        if existing and user_id and existing.get("user_id") == user_id and not existing.get("coins_awarded"):
            _award(db, repository, user_id, booking.id, existing)
        raise HTTPException(status_code=409, detail="You have already rated this trip")
    except Exception:
        logger.exception("Could not save review")
        raise HTTPException(status_code=503, detail="Could not save your rating. Please try again.")

    coins = _award(db, repository, user_id, booking.id, review)
    return {
        "booking_id": booking.id,
        "rating": review["rating"],
        "comment": review.get("comment"),
        "coins_awarded": coins,
    }


@router.post("/status")
def review_status(
    payload: ReviewStatusRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Which of my trips are already rated, and what a rating is worth."""
    repository = get_review_repository(request.app)
    if repository is None:
        return {"enabled": False, "reward_coins": 0, "reviews": {}}

    # Only my own bookings are looked up.
    own = set(
        db.scalars(
            select(Booking.id).where(
                Booking.id.in_(payload.booking_ids), Booking.user_id == str(current_user.id)
            )
        ).all()
    )
    try:
        found = repository.get_reviews(list(own))
        reward = repository.get_reward_coins()
    except Exception:
        logger.exception("Review status failed")
        return {"enabled": False, "reward_coins": 0, "reviews": {}}

    return {
        "enabled": True,
        "reward_coins": reward,
        "reviews": {
            bid: {"rating": r.get("rating"), "comment": r.get("comment")}
            for bid, r in found.items()
        },
    }


# ---------------------------------------------------------------- admin

@router.get("/admin/reward", dependencies=[Depends(require_admin)])
def get_reward(request: Request):
    return {"coins": _repository(request).get_reward_coins()}


@router.put("/admin/reward", dependencies=[Depends(require_admin)])
def set_reward(payload: RewardUpdateRequest, request: Request):
    """Change the coins given for a review. Applies to the next rating, no redeploy."""
    _repository(request).set_reward_coins(payload.coins)
    return {"coins": payload.coins}