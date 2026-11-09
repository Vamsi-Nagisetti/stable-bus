
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models.Refund import Refund


class RefundRepository:

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

    def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> Refund | None:
        return self.database.scalar(
            select(Refund).where(
                Refund.idempotency_key == idempotency_key
            )
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
        result = self.database.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0))
            .where(
                Refund.payment_id == payment_id,
             Refund.status.in_([
    "PENDING",
    "PROCESSING",
    "UNKNOWN",
    "SUCCESS",
]),
            )
        )

        return result

    def update_status(
        self,
        refund_id: str,
        status: str,
        gateway_refund_id: str | None = None,
    ) -> Refund | None:

        refund = self.get_by_id(refund_id)

        if not refund:
            return None

        refund.status = status

        if gateway_refund_id:
            refund.gateway_refund_id = gateway_refund_id

        self.database.flush()

        return refund
