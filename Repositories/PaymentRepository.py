
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.Payment import Payment


class PaymentRepository:
    RECONCILABLE_STATUSES = ("PROCESSING", "PENDING", "UNKNOWN")

    def __init__(self, database: Session):
        self.database = database

    def create(self, payment: Payment) -> Payment:
        self.database.add(payment)
        self.database.flush()
        return payment

    def get_by_id(self, payment_id: str) -> Payment | None:
        return self.database.scalar(
            select(Payment).where(Payment.id == payment_id)
        )

    def get_by_attempt_id(self, payment_attempt_id: str) -> Payment | None:
        return self.database.scalar(
            select(Payment).where(
                Payment.payment_attempt_id == payment_attempt_id
            )
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        return self.database.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )

    def get_by_gateway_order_id(self, gateway_order_id: str) -> Payment | None:
        return self.database.scalar(
            select(Payment).where(Payment.gateway_order_id == gateway_order_id)
        )

    def update_status(
        self,
        payment_id: str,
        status: str,
        gateway_payment_id: str | None = None,
    ) -> Payment | None:
        payment = self.get_by_id(payment_id)
        if payment is None:
            return None

        payment.status = status
        if gateway_payment_id:
            payment.gateway_payment_id = gateway_payment_id

        if status in ("SUCCESS", "FAILED", "MANUAL_REVIEW"):
            payment.reconciliation_locked_until = None

        self.database.flush()
        return payment

    def get_by_id_for_update(self, payment_id: str) -> Payment | None:
        return self.database.scalar(
            select(Payment)
            .where(Payment.id == payment_id)
            .with_for_update()
        )

    def claim_due_for_reconciliation(
        self,
        limit: int = 100,
        lease_seconds: int = 120,
        now: datetime | None = None,
    ) -> list[Payment]:
        now = now or datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)

        stmt = (
            select(Payment)
            .where(
                Payment.status.in_(self.RECONCILABLE_STATUSES),
                Payment.next_reconciliation_at <= now,
                Payment.reconciliation_deadline_at > now,
                or_(
                    Payment.reconciliation_locked_until.is_(None),
                    Payment.reconciliation_locked_until <= now,
                ),
            )
            .order_by(Payment.next_reconciliation_at, Payment.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        payments = list(self.database.scalars(stmt).all())

        for payment in payments:
            payment.reconciliation_locked_until = lease_until
            payment.reconciliation_attempts += 1
            payment.last_reconciled_at = now

        self.database.flush()
        return payments

    def schedule_reconciliation(
        self,
        payment_id: str,
        next_at: datetime,
        error: str | None = None,
    ) -> Payment | None:
        payment = self.get_by_id_for_update(payment_id)
        if payment is None:
            return None

        if payment.status in ("SUCCESS", "FAILED", "MANUAL_REVIEW"):
            payment.reconciliation_locked_until = None
            return payment

        payment.next_reconciliation_at = next_at
        payment.reconciliation_locked_until = None
        payment.last_reconciliation_error = (error or "")[:2000] or None
        self.database.flush()
        return payment

    def mark_manual_review(
        self,
        payment_id: str,
        reason: str,
    ) -> Payment | None:
        payment = self.get_by_id_for_update(payment_id)
        if payment is None:
            return None

        payment.status = "MANUAL_REVIEW"
        payment.reconciliation_locked_until = None
        payment.last_reconciliation_error = reason[:2000]
        self.database.flush()
        return payment
