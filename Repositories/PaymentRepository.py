
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.Payment import Payment


class PaymentRepository:

    def __init__(self, database: Session):
        self.database = database

    def create(self, payment: Payment) -> Payment:
        self.database.add(payment)
        self.database.flush()
        return payment

    def get_by_id(self, payment_id: str) -> Payment | None:
        stmt = select(Payment).where(
            Payment.id == payment_id
        )
        return self.database.scalar(stmt)

    def get_by_attempt_id(
        self, payment_attempt_id: str
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.payment_attempt_id == payment_attempt_id
        )
        return self.database.scalar(stmt)

    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.idempotency_key == idempotency_key
        )
        return self.database.scalar(stmt)

    def get_by_gateway_order_id(
        self, gateway_order_id: str
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.gateway_order_id == gateway_order_id
        )
        return self.database.scalar(stmt)

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

        self.database.flush()
        return payment
    
    def get_by_id_for_update(self, payment_id: str):
        return self.database.scalar(
            select(Payment)
            .where(Payment.id == payment_id)
            .with_for_update()
        )