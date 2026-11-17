
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models.Refund import Refund


class RefundRepository:
    RECONCILABLE_STATUSES = ("PENDING", "PROCESSING", "UNKNOWN")

    def __init__(self, database: Session):
        self.database = database

    def create(self, refund: Refund) -> Refund:
        self.database.add(refund)
        self.database.flush()
        return refund

    def get_by_id(self, refund_id: str) -> Refund | None:
        return self.database.scalar(
            select(Refund).where(Refund.id == refund_id)
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> Refund | None:
        return self.database.scalar(
            select(Refund).where(Refund.idempotency_key == idempotency_key)
        )

    def get_by_payment_id(self, payment_id: str) -> list[Refund]:
        return list(
            self.database.scalars(
                select(Refund)
                .where(Refund.payment_id == payment_id)
                .order_by(Refund.created_at.desc())
            ).all()
        )

    def get_total_refunded_amount(self, payment_id: str):
        return self.database.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.payment_id == payment_id,
                Refund.status.in_(
                    ("PENDING", "PROCESSING", "UNKNOWN", "SUCCESS")
                ),
            )
        )

    def update_status(
        self,
        refund_id: str,
        status: str,
        gateway_refund_id: str | None = None,
    ) -> Refund | None:
        refund = self.get_by_id(refund_id)
        if refund is None:
            return None

        refund.status = status
        if gateway_refund_id:
            refund.gateway_refund_id = gateway_refund_id

        if status in ("SUCCESS", "FAILED", "MANUAL_REVIEW"):
            refund.reconciliation_locked_until = None

        self.database.flush()
        return refund

    def claim_due_for_reconciliation(
        self,
        limit: int = 100,
        lease_seconds: int = 120,
        now: datetime | None = None,
    ) -> list[Refund]:
        now = now or datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)

        stmt = (
            select(Refund)
            .where(
                Refund.status.in_(self.RECONCILABLE_STATUSES),
                Refund.next_reconciliation_at <= now,
                Refund.reconciliation_deadline_at > now,
                or_(
                    Refund.reconciliation_locked_until.is_(None),
                    Refund.reconciliation_locked_until <= now,
                ),
            )
            .order_by(Refund.next_reconciliation_at, Refund.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        refunds = list(self.database.scalars(stmt).all())

        for refund in refunds:
            refund.reconciliation_locked_until = lease_until
            refund.reconciliation_attempts += 1
            refund.last_reconciled_at = now

        self.database.flush()
        return refunds

    def schedule_reconciliation(
        self,
        refund_id: str,
        next_at: datetime,
        error: str | None = None,
    ) -> Refund | None:
        refund = self.database.scalar(
            select(Refund)
            .where(Refund.id == refund_id)
            .with_for_update()
        )
        if refund is None:
            return None

        if refund.status in ("SUCCESS", "FAILED", "MANUAL_REVIEW"):
            refund.reconciliation_locked_until = None
            return refund

        refund.next_reconciliation_at = next_at
        refund.reconciliation_locked_until = None
        refund.last_reconciliation_error = (error or "")[:2000] or None
        self.database.flush()
        return refund

    def mark_manual_review(
        self,
        refund_id: str,
        reason: str,
    ) -> Refund | None:
        refund = self.database.scalar(
            select(Refund)
            .where(Refund.id == refund_id)
            .with_for_update()
        )
        if refund is None:
            return None

        refund.status = "MANUAL_REVIEW"
        refund.reconciliation_locked_until = None
        refund.last_reconciliation_error = reason[:2000]
        self.database.flush()
        return refund
