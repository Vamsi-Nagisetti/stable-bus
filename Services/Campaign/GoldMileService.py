"""Gold Mile: complete a few trips, get a chance to win 1 gram of gold.

Who needs how many trips
------------------------
* PRE_REGISTERED : the user's mobile is on the pre-registration list      -> 2 trips
* FIRST_TIME     : new to StableBus (no confirmed booking before the campaign start) -> 3 trips
* REGULAR        : already travelled with us before the campaign started  -> 4 trips

A trip counts once it is completed (CONFIRMED booking whose journey date has passed) and its
journey date falls inside the user's CURRENT 90-day cycle. A cycle starts on the user's first trip
and a new one (progress back to 0) starts every 90 days. Upcoming confirmed trips are reported
separately so the app can show them as "on the way".

Environment
-----------
GOLD_MILE_START   launch day, YYYY-MM-DD (IST). Only used to tell new travellers from existing
                  ones (a confirmed booking made BEFORE it = existing). Default: 2026-11-27
GOLD_MILE_DAYS    length of one cycle in days. Default: 90
GOLD_MILE_ENABLED set to 0/false to hide the section.
GOLD_MILE_PRE_REGISTERED_TRIPS / GOLD_MILE_FIRST_TIME_TRIPS / GOLD_MILE_REGULAR_TRIPS (2 / 3 / 4)
"""
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.constants.booking_status import BookingStatus
from models.Booking import Booking
from models.PreRegisteredUser import PreRegisteredUser

IST = ZoneInfo("Asia/Kolkata")


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _start() -> date:
    raw = os.getenv("GOLD_MILE_START", "2026-11-27").strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return date(2026, 11, 27)


def enabled() -> bool:
    return os.getenv("GOLD_MILE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _today() -> date:
    return datetime.now(IST).date()


class GoldMileService:
    def __init__(self, db: Session):
        self.db = db

    def _is_pre_registered(self, mobile: str | None) -> bool:
        if not mobile:
            return False
        digits = "".join(ch for ch in str(mobile) if ch.isdigit())[-10:]
        if len(digits) != 10:
            return False
        return (
            self.db.scalar(
                select(func.count())
                .select_from(PreRegisteredUser)
                .where(PreRegisteredUser.mobile == digits)
            )
            or 0
        ) > 0

    def _travelled_before(self, user_id: str, start: date) -> bool:
        """Any confirmed booking made before the campaign started."""
        start_utc = datetime(start.year, start.month, start.day, tzinfo=IST).astimezone(timezone.utc)
        return (
            self.db.scalar(
                select(func.count())
                .select_from(Booking)
                .where(
                    Booking.user_id == str(user_id),
                    Booking.status == BookingStatus.CONFIRMED,
                    Booking.created_at < start_utc,
                )
            )
            or 0
        ) > 0

    def _first_trip_date(self, user_id: str) -> date | None:
        """Journey date of the user's earliest confirmed trip (their cycle starts there)."""
        return self.db.scalar(
            select(func.min(Booking.journey_date)).where(
                Booking.user_id == str(user_id),
                Booking.status == BookingStatus.CONFIRMED,
            )
        )

    def progress(self, user) -> dict:
        """Tier + progress inside the user's CURRENT 90-day cycle.

        Cycles are GOLD_MILE_DAYS long and start on the user's first trip, so progress resets by itself
        every 90 days (first trip -> +90 days -> next cycle starts at 0, and so on).
        """
        launch = _start()
        days = _int_env("GOLD_MILE_DAYS", 90)
        today = _today()
        user_id = str(user.id)

        if self._is_pre_registered(getattr(user, "mobile_number", None)):
            tier, required = "PRE_REGISTERED", _int_env("GOLD_MILE_PRE_REGISTERED_TRIPS", 2)
        elif self._travelled_before(user_id, launch):
            tier, required = "REGULAR", _int_env("GOLD_MILE_REGULAR_TRIPS", 4)
        else:
            tier, required = "FIRST_TIME", _int_env("GOLD_MILE_FIRST_TIME_TRIPS", 3)

        anchor = self._first_trip_date(user_id)
        if anchor is None or anchor > today:
            cycle_start = today
            cycle_index = 0
        else:
            cycle_index = (today - anchor).days // days
            cycle_start = anchor + timedelta(days=cycle_index * days)
        cycle_end = cycle_start + timedelta(days=days)

        in_cycle = [
            Booking.user_id == user_id,
            Booking.status == BookingStatus.CONFIRMED,
            Booking.journey_date >= cycle_start,
            Booking.journey_date < cycle_end,
        ]
        completed = (
            self.db.scalar(
                select(func.count()).select_from(Booking).where(*in_cycle, Booking.journey_date < today)
            )
            or 0
        )
        upcoming = (
            self.db.scalar(
                select(func.count()).select_from(Booking).where(*in_cycle, Booking.journey_date >= today)
            )
            or 0
        )

        has_cycle = anchor is not None
        return {
            "enabled": enabled(),
            "state": "ACTIVE",
            "tier": tier,
            "required_trips": int(required),
            "completed_trips": int(min(completed, required)),
            "total_completed_trips": int(completed),
            "upcoming_trips": int(upcoming),
            "qualified": bool(completed >= required),
            "cycle": int(cycle_index + 1),
            "starts_on": cycle_start.isoformat() if has_cycle else None,
            "ends_on": (cycle_end - timedelta(days=1)).isoformat() if has_cycle else None,
            "days_left": max(0, (cycle_end - today).days) if has_cycle else None,
        }