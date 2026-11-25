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


def max_redeem_percent() -> Decimal:
    """Max share of a ticket payable with coins (env, default 100)."""
    try:
        value = Decimal(os.getenv("WALLET_MAX_REDEEM_PERCENT", "100"))
    except Exception:
        value = Decimal("100")
    return min(max(value, Decimal("0")), Decimal("100"))


def earn_basis() -> str:
    """'total' (default): earn on the full ticket price.
    'cash': earn only on the part paid in cash (coins-paid part earns nothing)."""
    return os.getenv("WALLET_EARN_BASIS", "total").strip().lower()


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
        """Customer-facing activity: ONE line per real-world event.

        * all lots consumed by one payment            -> one debit
        * all lots refilled by one cancellation       -> one credit
        * debit status: PENDING until the trip date has passed, then USED;
          RETURNED once the ticket was cancelled.
        * coins taken and returned because a payment failed are hidden
          (from the customer's point of view that never happened).
        """
        rows = self.db.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user_id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(2000)
        ).all()

        payment_ids = {r.payment_id for r in rows if r.payment_id}
        payments = {
            p.id: p
            for p in (
                self.db.scalars(
                    select(Payment).where(Payment.id.in_(payment_ids))
                ).all()
                if payment_ids else []
            )
        }
        booking_ids = {r.booking_id for r in rows if r.booking_id}
        bookings = {
            b.id: b
            for b in (
                self.db.scalars(
                    select(Booking)
                    .options(noload(Booking.passengers))
                    .where(Booking.id.in_(booking_ids))
                ).all()
                if booking_ids else []
            )
        }
        today = today_ist()

        def dead_payment(pid):
            pay = payments.get(pid)
            return pay is not None and pay.status in ("FAILED",)

        items: dict[tuple, dict] = {}
        for r in rows:
            moment = _aware(r.created_at)

            if r.type in ("REDEEM", "REVERSE", "RESTORE") and r.payment_id:
                if dead_payment(r.payment_id):
                    continue  # coins held for a payment that failed

            if r.type == "REDEEM":
                key = ("REDEEM", r.booking_id or r.payment_id)
                item = items.setdefault(key, {
                    "id": f"redeem-{r.booking_id or r.payment_id}", "type": "REDEEM",
                    "coins": 0, "booking_id": r.booking_id,
                    "payment_id": r.payment_id,
                    "description": "Coins used for a ticket",
                    "created_at": moment,
                })
                item["coins"] += r.coins
                item["created_at"] = min(item["created_at"], moment)

            elif r.type in ("REVERSE", "RESTORE"):
                if r.coins == 0:
                    continue  # internal marker row
                key = ("RETURN", r.payment_id, moment.replace(microsecond=0))
                item = items.setdefault(key, {
                    "id": f"return-{r.payment_id}-{int(moment.timestamp())}",
                    "type": "RETURN", "coins": 0,
                    "booking_id": r.booking_id, "payment_id": r.payment_id,
                    "description": "Coins returned after cancellation",
                    "created_at": moment,
                })
                item["coins"] += r.coins

            else:
                items[(r.type, r.id)] = {
                    "id": r.id, "type": r.type, "coins": r.coins,
                    "booking_id": r.booking_id, "payment_id": r.payment_id,
                    "description": r.description, "created_at": moment,
                }

        # Status of the debits.
        returned_by_payment: dict[str, int] = {}
        for it in items.values():
            if it["type"] == "RETURN" and it["payment_id"]:
                returned_by_payment[it["payment_id"]] = (
                    returned_by_payment.get(it["payment_id"], 0) + it["coins"]
                )
        for it in items.values():
            if it["type"] != "REDEEM":
                continue
            booking = bookings.get(it["booking_id"])
            used = -it["coins"]
            if returned_by_payment.get(it["payment_id"], 0) >= used:
                it["status"] = "RETURNED"
            elif (
                booking is not None
                and booking.journey_date
                and booking.journey_date < today
                and booking.status == BookingStatus.CONFIRMED
            ):
                it["status"] = "USED"
            else:
                it["status"] = "PENDING"
            if booking is not None and booking.journey_date:
                it["journey_date"] = booking.journey_date.isoformat()

        ordered = sorted(
            items.values(), key=lambda i: i["created_at"], reverse=True
        )[offset:offset + limit]
        for it in ordered:
            it["created_at"] = it["created_at"].isoformat()
        return ordered

    # ------------------------------------------------------------------
    # Earning
    # ------------------------------------------------------------------
    @staticmethod
    def coins_for_booking(
        booking: Booking, cash_ratio: Decimal = Decimal("1")
    ) -> int:
        """Coins earned for a (completed) booking."""
        total = Decimal(str(booking.total_amount)) * cash_ratio
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

    def _cash_ratio(self, booking: Booking) -> Decimal:
        if earn_basis() != "cash":
            return Decimal("1")
        payment = self.db.scalars(
            select(Payment).where(
                Payment.booking_id == booking.id, Payment.status == "SUCCESS"
            ).order_by(Payment.created_at.desc())
        ).first()
        if payment is None:
            return Decimal("1")
        cash = Decimal(str(payment.amount))
        paid = cash + Decimal(str(payment.coin_value or 0))
        return (cash / paid) if paid > 0 else Decimal("1")

    def credit_booking_if_eligible(self, booking: Booking) -> int:
        """Credit coins for one booking. Idempotent. Returns coins credited."""
        if not booking.user_id:
            return 0  # guest booking - no wallet
        if booking.status != BookingStatus.CONFIRMED:
            return 0  # cancelled / failed / not ticketed
        if not booking.journey_date or booking.journey_date >= today_ist():
            return 0  # trip not completed yet

        coins = self.coins_for_booking(booking, self._cash_ratio(booking))
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

    @staticmethod
    def _unpaid_at_gateway(payment: Payment, provider) -> bool:
        """True only when we are SURE no money was captured for this payment."""
        if not payment.gateway_order_id:
            # never reached the gateway; give a create-order retry time
            return _aware(payment.created_at) < (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            )
        if provider is None:
            return False
        try:
            found = provider.get_payments_for_order(payment.gateway_order_id)
        except Exception:
            return False  # unknown -> keep the hold
        if not isinstance(found, list):
            return False
        return not any(
            str(i.get("status", "")).lower() in ("captured", "authorized")
            for i in found
        )

    def release_unpaid_holds(
        self,
        booking_id: str,
        provider,
        older_than_minutes: int = 0,
    ) -> int:
        """Free coins held by earlier, never-paid attempts of a booking."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        payments = self.db.scalars(
            select(Payment).where(
                Payment.booking_id == booking_id,
                Payment.coins_used > 0,
                Payment.status.in_(("CREATED", "PROCESSING", "PENDING", "UNKNOWN")),
            )
        ).all()
        return self._release_unpaid(payments, provider, cutoff)

    def _release_unpaid(self, payments, provider, cutoff) -> int:
        released = 0
        for payment in payments:
            try:
                if _aware(payment.created_at) > cutoff:
                    continue
                if not self._unpaid_at_gateway(payment, provider):
                    continue
                payment.status = "FAILED"
                payment.last_reconciliation_error = (
                    "Abandoned attempt - coins released"
                )
                self.db.commit()
                released += self.reverse_redemption(
                    payment.id, "Payment not completed - coins returned"
                )
            except Exception:
                self.db.rollback()
                logger.exception(
                    "Failed to release coins payment_id=%s", payment.id
                )
        return released

    def release_abandoned_redemptions(
        self, provider=None, stale_minutes: int = 45
    ) -> int:
        """Return coins held by payments that can no longer succeed."""
        now = datetime.now(timezone.utc)
        released = 0

        # 1. Payments already FAILED: just give the coins back.
        failed = self.db.scalars(
            select(Payment).where(
                Payment.coins_used > 0, Payment.status == "FAILED"
            ).limit(200)
        ).all()
        for payment in failed:
            try:
                released += self.reverse_redemption(
                    payment.id, "Payment failed - coins returned"
                )
            except Exception:
                self.db.rollback()
                logger.exception("Failed to release coins payment_id=%s", payment.id)

        # 2. Unfinished payments: release only if the gateway confirms no capture.
        open_payments = self.db.scalars(
            select(Payment).where(
                Payment.coins_used > 0,
                Payment.status.in_(("CREATED", "PROCESSING", "PENDING", "UNKNOWN")),
            ).limit(200)
        ).all()
        released += self._release_unpaid(
            open_payments, provider, now - timedelta(minutes=stale_minutes)
        )

        # 3. MANUAL_REVIEW older than 48h whose booking never progressed.
        reviews = self.db.scalars(
            select(Payment).where(
                Payment.coins_used > 0, Payment.status == "MANUAL_REVIEW"
            ).limit(100)
        ).all()
        for payment in reviews:
            booking = self.db.get(Booking, payment.booking_id)
            if (
                booking is not None
                and booking.status in (
                    BookingStatus.PAYMENT_PENDING,
                    BookingStatus.TEMP_BOOKED,
                    BookingStatus.BOOKING_FAILED,
                    BookingStatus.CANCELLED,
                )
                and _aware(payment.created_at) < now - timedelta(hours=48)
            ):
                try:
                    released += self.reverse_redemption(
                        payment.id, "Payment not completed - coins returned"
                    )
                except Exception:
                    self.db.rollback()
        return released

    # ------------------------------------------------------------------
    # Per-ticket coin summary (shown quietly on booking history)
    # ------------------------------------------------------------------
    def booking_coin_summary(self, bookings: list[Booking]) -> dict[str, dict]:
        ids = [b.id for b in bookings]
        if not ids:
            return {}
        today = today_ist()

        payments = self.db.scalars(
            select(Payment).where(
                Payment.booking_id.in_(ids),
                Payment.status == "SUCCESS",
                Payment.coins_used > 0,
            )
        ).all()
        pay_to_booking = {p.id: p.booking_id for p in payments}

        used: dict[str, int] = {}
        returned: dict[str, int] = {}
        if pay_to_booking:
            for tx in self.db.scalars(
                select(WalletTransaction).where(
                    WalletTransaction.payment_id.in_(list(pay_to_booking)),
                    WalletTransaction.type.in_(("REDEEM", "REVERSE", "RESTORE")),
                )
            ).all():
                bid = pay_to_booking[tx.payment_id]
                if tx.type == "REDEEM":
                    used[bid] = used.get(bid, 0) - tx.coins
                else:
                    returned[bid] = returned.get(bid, 0) + tx.coins

        earned: dict[str, int] = {}
        for tx in self.db.scalars(
            select(WalletTransaction).where(
                WalletTransaction.booking_id.in_(ids),
                WalletTransaction.type == "EARN",
            )
        ).all():
            earned[tx.booking_id] = earned.get(tx.booking_id, 0) + tx.coins

        out: dict[str, dict] = {}
        for b in bookings:
            u, r, e = used.get(b.id, 0), returned.get(b.id, 0), earned.get(b.id, 0)
            expected = 0
            if (
                b.user_id and e == 0
                and b.status == BookingStatus.CONFIRMED
                and b.journey_date and b.journey_date >= today
            ):
                expected = self.coins_for_booking(b, self._cash_ratio(b))

            if not (u or r or e or expected):
                continue

            info: dict = {}
            if u:
                info["coins_used"] = u
                if r >= u:
                    info["coins_state"] = "RETURNED"
                elif (
                    b.journey_date and b.journey_date < today
                    and b.status == BookingStatus.CONFIRMED
                ):
                    info["coins_state"] = "USED"
                else:
                    info["coins_state"] = "PENDING"
            if r:
                info["coins_returned"] = r
            if e:
                info["coins_earned"] = e
            if expected:
                info["coins_expected"] = expected
            out[b.id] = info
        return out

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
