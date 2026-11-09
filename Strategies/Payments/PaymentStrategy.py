
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class PaymentStrategy(ABC):

    @abstractmethod
    def create_order(
        self,
        order_id: str,
        amount: Decimal,
        customer: dict[str, Any],
        idempotency_key: str,
        currency: str = "INR",
        return_url: str | None = None,
    ) -> dict[str, Any]:
        """Create a payment order with the gateway."""
        raise NotImplementedError

    @abstractmethod
    def verify_payment(self, **kwargs) -> dict[str, Any]:
        """Verify payment signature and retrieve payment status."""
        raise NotImplementedError

    @abstractmethod
    def get_payment_status(
        self,
        payment_reference: str,
    ) -> dict[str, Any]:
        """Fetch the latest payment status from the gateway."""
        raise NotImplementedError

    @abstractmethod
    def refund_payment(
        self,
        payment_reference: str,
        amount: Decimal,
        refund_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Initiate a full or partial refund."""
        raise NotImplementedError
