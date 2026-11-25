"""Refunds for cancelled seats: cash back to the gateway + coins back to wallet.

Policy
------
refund value  = seat share of the ticket price  -  provider cancellation charge
seat share    = total_amount x (cancelled seats / total seats)
provider fee  = AO Pay `cancellationPenaltyValues[].cancellation_Penalty` per
                cancelled ticket. Unit is set by CANCELLATION_PENALTY_MODE:
                  "amount"  -> rupees per ticket (default)
                  "percent" -> percent of that seat's share
The refund value is split in the same ratio the customer paid:
  coin part = refund x coin_value / (cash + coin_value)  -> back as coins
  cash part = the rest                                    -> gateway refund
Never raises: a failure here must not fail the cancellation itself.
"""
import hashlib
import logging
import os
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from sqlalchemy import select

from models.Payment import Payment
from Services.Wallet.WalletService import (
    COIN_VALUE_RUPEES,
    WalletService,
)

logger = logging.getLogger("stablebus.cancellation_refund")

TWO = Decimal("0.01")


def _penalty_total(result: dict, seats: set[str], seat_share: Decimal) -> Decimal:
    mode = os.getenv("CANCELLATION_PENALTY_MODE", "amount").lower()
    total = Decimal("0")
    for item in (result or {}).get("cancellationPenaltyValues") or []:
        if str(item.get("seat_Number")) not in seats:
            continue
        try:
            value = Decimal(str(item.get("cancellation_Penalty", "0")))
        except Exception:
            continue
        if value < 0:
            continue
        total += (seat_share * value / Decimal(100)) if mode == "percent" else value
    return total


def process_cancellation_refund(
    db,
    payment_service,
    booking,
    cancelled_seats: set[str],
    provider_result: dict,
) -> dict:
    summary = {
        "refund_amount": "0.00",
        "refund_cash": "0.00",
        "refund_coins": 0,
        "cancellation_charge": "0.00",
        "status": "NOT_APPLICABLE",
    }
    try:
        payment = db.scalars(
            select(Payment)
            .where(Payment.booking_id == booking.id, Payment.status == "SUCCESS")
            .order_by(Payment.created_at.desc())
        ).first()
        if payment is None or not cancelled_seats:
            return summary

        seats = [str(s) for s in (booking.seat_numbers or [])]
        if not seats:
            return summary

        total = Decimal(str(booking.total_amount))
        seat_share = (total / Decimal(len(seats))).quantize(TWO, ROUND_HALF_UP)
        gross = seat_share * Decimal(len(cancelled_seats))
        penalty = _penalty_total(provider_result, cancelled_seats, seat_share)
        refund_value = max(Decimal("0"), gross - penalty).quantize(TWO, ROUND_HALF_UP)

        summary["cancellation_charge"] = str(penalty.quantize(TWO))
        summary["refund_amount"] = str(refund_value)
        if refund_value <= 0:
            summary["status"] = "NO_REFUND"
            return summary

        paid_cash = Decimal(str(payment.amount))
        coin_value = Decimal(str(payment.coin_value or 0))
        paid_total = paid_cash + coin_value
        ratio = (coin_value / paid_total) if paid_total > 0 else Decimal("0")

        coins = int(
            ((refund_value * ratio) / COIN_VALUE_RUPEES).to_integral_value(ROUND_DOWN)
        )
        cash = refund_value - coins * COIN_VALUE_RUPEES
        if payment.gateway == "WALLET":
            cash = Decimal("0")
        cash = cash.quantize(TWO)

        key = hashlib.sha1(
            f"{booking.id}:{','.join(sorted(cancelled_seats))}".encode()
        ).hexdigest()

        status = "REFUND_INITIATED"
        if coins > 0:
            WalletService(db).restore_coins(
                payment.id, coins, f"cancel:{key}",
                "Ticket cancelled - coins refunded",
            )
        summary["refund_coins"] = coins

        if cash > 0:
            res = payment_service.refund_payment(
                payment_id=payment.id,
                amount=cash,
                idempotency_key=f"cancel-refund:{key}",
            )
            summary["refund_cash"] = str(cash)
            summary["refund_status"] = res.get("status")
        summary["status"] = status
        return summary

    except Exception:
        db.rollback()
        logger.exception(
            "Cancellation refund failed booking_id=%s - needs manual review",
            getattr(booking, "id", None),
        )
        summary["status"] = "FAILED_NEEDS_REVIEW"
        return summary
