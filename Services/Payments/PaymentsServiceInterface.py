
from abc import ABC, abstractmethod
from typing import Any
from decimal import Decimal

class PaymentServiceInterface(ABC):

    @abstractmethod
    def initiate_payment(
        self,
        booking_id: str,
        idempotency_key: str,
        customer: dict[str, Any],
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def verify_payment(
        self,
        payment_id: str,
        gateway_payment_id: str,
        signature: str,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def refund_payment(
        self,
        payment_id: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> dict[str, Any]:
        pass
