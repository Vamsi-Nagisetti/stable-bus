"""StableBus wallet (coins).

Rules implemented
-----------------
* Earn: flat 2.5% of the ticket total, credited as coins AFTER the trip is
  completed. 1 coin = Rs 0.25 (4 coins = Re 1), so coins = floor(total * 0.1).
* No coins for cancelled tickets. Partially cancelled bookings earn only on
  the seats that were actually travelled (prorated by seat count).
* Coins expire on 1 January (IST) after they were earned (lots).
* Coins can pay for a ticket (1 coin = Rs 0.25). Oldest-expiry lots are used
  first (FIFO by expiry).

Money maths is done with Decimal / integers only.
"""
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, noload

from core.constants.booking_status import BookingStatus
from models.Booking import Booking
from models.BookingPassenger import BookingPassenger  # noqa: F401 (mapper registry)
from models.Payment import Payment
from models.Wallet import WalletLot, WalletTransaction

logger = logging.getLogger("stablebus.wallet")

IST = ZoneInfo("Asia/Kolkata")

COIN_VALUE_RUPEES = Decimal("0.25")          # 1 coin = Rs 0.25
EARN_RATE = Decimal(os.getenv("WALLET_EARN_RATE", "0.025"))  # 2.5%
MIN_CASH_PORTION = Decimal("1.00")           # gateway minimum (Re 1)


class WalletError(ValueError):
    """Business-rule violation (mapped to HTTP 400 by the routes)."""


def today_ist() -> date:
    return datetime.now(IST).date()


def next_jan_1(moment: datetime) -> datetime:
    """The first 1 January 00:00 IST strictly after `moment` (as UTC)."""
    local = moment.astimezone(IST)
    return datetime(local.year + 1, 1, 1, tzinfo=IST).astimezone(timezone.utc)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def coins_to_rupees(coins: int) -> Decimal:
    return (Decimal(coins) * COIN_VALUE_RUPEES).quantize(Decimal("0.01"))


class WalletService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def _active_lots_query(self, user_id: str, now: datetime):
        return select(WalletLot).where(
            WalletLot.user_id == user_id,
            WalletLot.status == "ACTIVE",
            WalletLot.coins_remaining > 0,
            WalletLot.expires_at > now,
        )

    def get_balance(self, user_id: str) -> dict:
        now = datetime.now(timezone.utc)
        lots = self.db.scalars(
            self._active_lots_query(user_id, now).order_by(WalletLot.expires_at)
        ).all()
        total = sum(l.coins_remaining for l in lots)

        expiring = None
        if lots:
            first = _aware(lots[0].expires_at)
            expiring = {
                "coins": sum(
                    l.coins_remaining for l in lots if _aware(l.expires_at) == first
                ),
                "expires_at": first.isoformat(),
            }

        return {
            "coins": int(total),
            "rupee_value": str(coins_to_rupees(total)),
            "coin_value_rupees": str(COIN_VALUE_RUPEES),
            "next_expiry": expiring,
        }

    def get_transactions(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> list[dict]:
        rows = self.db.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user_id)
            .order_by(
                WalletTransaction.created_at.desc(),
                WalletTransaction.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return [
            {
                "id": r.id,
                "type": r.type,
                "coins": r.coins,
                "booking_id": r.booking_id,
                "payment_id": r.payment_id,
                "description": r.description,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Earning
    # ------------------------------------------------------------------
    @staticmethod
    def coins_for_booking(booking: Booking) -> int:
        """Coins earned for a (completed) booking."""
        total = Decimal(str(booking.total_amount))
        seats = [str(s) for s in (booking.seat_numbers or [])]
        cancelled = {str(s) for s in (booking.cancelled_seat_numbers or [])}

        if not seats or total <= 0:
            return 0

        active = [s for s in seats if s not in cancelled]
        if not active:
            return 0  # fully cancelled -> Rule 1

        earn_base = total * Decimal(len(active)) / Decimal(len(seats))
        rupees = earn_base * EARN_RATE
        return int(
            (rupees / COIN_VALUE_RUPEES).to_integral_value(rounding=ROUND_DOWN)
        )

    def _add_lot(
        self,
        user_id: str,
        coins: int,
        lot_key: str,
        source: str,
        tx_type: str,
        description: str,
        booking_id: str | None = None,
        payment_id: str | None = None,
    ) -> bool:
        """Insert lot + ledger row. Returns False if already done."""
        now = datetime.now(timezone.utc)
        lot = WalletLot(
            user_id=user_id,
            lot_key=lot_key,
            source=source,
            booking_id=booking_id,
            coins_total=coins,
            coins_remaining=coins,
            status="ACTIVE",
            earned_at=now,
            expires_at=next_jan_1(now),
        )
        try:
            with self.db.begin_nested():
                self.db.add(lot)
                self.db.flush()
                self.db.add(WalletTransaction(
                    user_id=user_id,
                    type=tx_type,
                    coins=coins,
                    lot_id=lot.id,
                    booking_id=booking_id,
                    payment_id=payment_id,
                    idempotency_key=lot_key,
                    description=description,
                ))
                self.db.flush()
        except IntegrityError:
            return False
        return True

    def credit_booking_if_eligible(self, booking: Booking) -> int:
        """Credit coins for one booking. Idempotent. Returns coins credited."""
        if not booking.user_id:
            return 0  # guest booking - no wallet
        if booking.status != BookingStatus.CONFIRMED:
            return 0  # cancelled / failed / not ticketed
        if not booking.journey_date or booking.journey_date >= today_ist():
            return 0  # trip not completed yet

        coins = self.coins_for_booking(booking)
        if coins <= 0:
            return 0

        created = self._add_lot(
            user_id=str(booking.user_id),
            coins=coins,
            lot_key=f"earn:{booking.id}",
            source="TRIP",
            tx_type="EARN",
            description=(
                f"2.5% reward for trip on {booking.journey_date.isoformat()}"
            ),
            booking_id=booking.id,
        )
        return coins if created else 0

    def credit_completed_trips(
        self, user_id: str | None = None, batch_size: int = 200
    ) -> list[dict]:
        """Credit every completed-but-not-yet-credited booking.

        Returns [{user_id, booking_id, coins}] for newly credited bookings
        so the caller can notify users.
        """
        credited: list[dict] = []
        already = select(WalletLot.booking_id).where(
            WalletLot.source == "TRIP", WalletLot.booking_id.is_not(None)
        )
        stmt = (
            select(Booking)
            .options(noload(Booking.passengers))
            .where(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.user_id.is_not(None),
                Booking.journey_date < today_ist(),
                Booking.id.not_in(already),
            )
            .order_by(Booking.journey_date)
            .limit(batch_size)
        )
        if user_id is not None:
            stmt = stmt.where(Booking.user_id == str(user_id))

        for booking in self.db.scalars(stmt).all():
            try:
                coins = self.credit_booking_if_eligible(booking)
                self.db.commit()
                if coins:
                    credited.append({
                        "user_id": str(booking.user_id),
                        "booking_id": booking.id,
                        "coins": coins,
                    })
            except Exception:
                self.db.rollback()
                logger.exception(
                    "Wallet credit failed booking_id=%s", booking.id
                )
        return credited

    def admin_credit(
        self, user_id: str, coins: int, reason: str, ref: str
    ) -> bool:
        if coins <= 0:
            raise WalletError("coins must be positive")
        created = self._add_lot(
            user_id=str(user_id),
            coins=coins,
            lot_key=f"adjust:{ref}",
            source="ADMIN",
            tx_type="ADJUST",
            description=reason[:300],
        )
        self.db.commit()
        return created

    # ------------------------------------------------------------------
    # Redemption (caller commits - keep it atomic with the Payment row)
    # ------------------------------------------------------------------
    def redeem(
        self,
        user_id: str,
        coins: int,
        payment_id: str,
        booking_id: str,
    ) -> None:
        if coins <= 0:
            return
        now = datetime.now(timezone.utc)
        lots = self.db.scalars(
            self._active_lots_query(user_id, now)
            .order_by(WalletLot.expires_at, WalletLot.earned_at)
            .with_for_update()
        ).all()

        available = sum(l.coins_remaining for l in lots)
        if coins > available:
            raise WalletError(
                f"Not enough coins. Available: {available}, requested: {coins}"
            )

        remaining = coins
        for lot in lots:
            if remaining == 0:
                break
            take = min(lot.coins_remaining, remaining)
            lot.coins_remaining -= take
            if lot.coins_remaining == 0:
                lot.status = "EXHAUSTED"
            remaining -= take
            self.db.add(WalletTransaction(
                user_id=user_id,
                type="REDEEM",
                coins=-take,
                lot_id=lot.id,
                booking_id=booking_id,
                payment_id=payment_id,
                idempotency_key=f"redeem:{payment_id}:{lot.id}",
                description="Coins used for ticket payment",
            ))
        self.db.flush()

    def reverse_redemption(self, payment_id: str, reason: str) -> int:
        """Give back ALL coins still held by `payment_id`. Idempotent."""
        return self.restore_coins(
            payment_id, None, f"reverse:{payment_id}", reason
        )

    def restore_coins(
        self,
        payment_id: str,
        coins: int | None,
        key: str,
        reason: str,
    ) -> int:
        """Return `coins` (None = everything outstanding) used by a payment.

        Coins go back into their original lot (keeping the original expiry)
        when that lot is still valid, otherwise into a fresh lot expiring on
        the next 1 Jan. Idempotent per `key`. Commits. Returns coins restored.
        """
        redeems = self.db.scalars(
            select(WalletTransaction).where(
                WalletTransaction.payment_id == payment_id,
                WalletTransaction.type == "REDEEM",
            ).order_by(WalletTransaction.created_at, WalletTransaction.id)
        ).all()
        if not redeems:
            return 0

        # Already restored for this exact request? (retry safety)
        done = self.db.scalar(
            select(func.count()).select_from(WalletTransaction).where(
                WalletTransaction.idempotency_key.like(f"{key}:%")
            )
        )
        if done:
            return 0

        user_id = redeems[0].user_id
        booking_id = redeems[0].booking_id
        returned = self.db.scalars(
            select(WalletTransaction).where(
                WalletTransaction.payment_id == payment_id,
                WalletTransaction.type.in_(("REVERSE", "RESTORE")),
            )
        ).all()
        total_used = sum(-t.coins for t in redeems)
        total_returned = sum(t.coins for t in returned)
        outstanding = total_used - total_returned
        want = outstanding if coins is None else min(int(coins), outstanding)
        if want <= 0:
            return 0

        returned_by_lot: dict[str, int] = {}
        for t in returned:
            if t.lot_id:
                returned_by_lot[t.lot_id] = returned_by_lot.get(t.lot_id, 0) + t.coins

        now = datetime.now(timezone.utc)
        left = want
        orphan = 0
        for tx in redeems:
            if left <= 0:
                break
            room = -tx.coins - returned_by_lot.get(tx.lot_id, 0)
            give = min(room, left)
            if give <= 0:
                continue
            left -= give
            lot = self.db.scalar(
                select(WalletLot).where(WalletLot.id == tx.lot_id)
                .with_for_update()
            )
            if (
                lot is not None
                and lot.status != "EXPIRED"
                and _aware(lot.expires_at) > now
            ):
                lot.coins_remaining += give
                lot.status = "ACTIVE"
                self.db.add(WalletTransaction(
                    user_id=user_id, type="REVERSE", coins=give,
                    lot_id=lot.id, booking_id=booking_id,
                    payment_id=payment_id,
                    idempotency_key=f"{key}:{lot.id}",
                    description=reason[:300],
                ))
            else:
                orphan += give
                # marker so retries of this key are recognised
                self.db.add(WalletTransaction(
                    user_id=user_id, type="REVERSE", coins=0,
                    lot_id=None, booking_id=booking_id,
                    payment_id=payment_id,
                    idempotency_key=f"{key}:expired:{tx.id}",
                    description="original lot expired",
                ))

        if orphan:
            self._add_lot(
                user_id=user_id,
                coins=orphan,
                lot_key=f"restore:{key}",
                source="RESTORE",
                tx_type="RESTORE",
                description=reason[:300],
                booking_id=booking_id,
                payment_id=payment_id,
            )

        self.db.commit()
        logger.info(
            "Wallet coins restored payment_id=%s coins=%s reason=%s",
            payment_id, want, reason,
        )
        return want

    # ------------------------------------------------------------------
    # Housekeeping jobs
    # ------------------------------------------------------------------
    def expire_due_lots(self, batch_size: int = 500) -> int:
        """Jan-1 expiry sweeper. Returns number of coins expired."""
        now = datetime.now(timezone.utc)
        lots = self.db.scalars(
            select(WalletLot)
            .where(
                WalletLot.status == "ACTIVE",
                WalletLot.expires_at <= now,
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()

        expired = 0
        for lot in lots:
            coins = lot.coins_remaining
            lot.status = "EXPIRED"
            lot.coins_remaining = 0
            if coins > 0:
                self.db.add(WalletTransaction(
                    user_id=lot.user_id, type="EXPIRE", coins=-coins,
                    lot_id=lot.id,
                    idempotency_key=f"expire:{lot.id}",
                    description="Coins expired on 1 January",
                ))
                expired += coins
        self.db.commit()
        return expired

    def release_abandoned_redemptions(self, stale_hours: int = 6) -> int:
        """Return coins held by payments that can no longer succeed."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
        payments = self.db.scalars(
            select(Payment)
            .where(
                Payment.coins_used > 0,
                (
                    Payment.status.in_(("FAILED", "MANUAL_REVIEW"))
                    | (
                        Payment.status.in_(("CREATED", "PROCESSING"))
                        & (Payment.created_at < cutoff)
                    )
                ),
            )
            .limit(200)
        ).all()

        released = 0
        for payment in payments:
            try:
                # MANUAL_REVIEW may still turn into a real capture, so only
                # release it when the booking never progressed past payment
                # and the payment is old enough (48h).
                if payment.status == "MANUAL_REVIEW":
                    booking = self.db.get(Booking, payment.booking_id)
                    if (
                        booking is None
                        or booking.status not in (
                            BookingStatus.PAYMENT_PENDING,
                            BookingStatus.TEMP_BOOKED,
                            BookingStatus.BOOKING_FAILED,
                            BookingStatus.CANCELLED,
                        )
                        or _aware(payment.created_at)
                        > datetime.now(timezone.utc) - timedelta(hours=48)
                    ):
                        continue
                released += self.reverse_redemption(
                    payment.id, f"Payment {payment.status.lower()}"
                )
            except Exception:
                self.db.rollback()
                logger.exception(
                    "Failed to release coins payment_id=%s", payment.id
                )
        return released

    # ------------------------------------------------------------------
    # Trip statistics
    # ------------------------------------------------------------------
    def trip_stats(self, user_id: str, days: int | None = None) -> dict:
        """Completed trips = CONFIRMED bookings whose journey date has passed.

        Counts bookings (a trip), not seats. `days` limits to trips whose
        journey date falls in the last `days` days.
        """
        today = today_ist()
        base = [
            Booking.user_id == str(user_id),
            Booking.status == BookingStatus.CONFIRMED,
            Booking.journey_date < today,
        ]
        total = self.db.scalar(
            select(func.count()).select_from(Booking).where(*base)
        ) or 0
        result = {"total_completed_trips": int(total)}

        if days is not None:
            since = today - timedelta(days=days)
            recent = self.db.scalar(
                select(func.count()).select_from(Booking).where(
                    *base, Booking.journey_date >= since
                )
            ) or 0
            result["days"] = days
            result["completed_trips_in_period"] = int(recent)
            result["since"] = since.isoformat()
        return result
