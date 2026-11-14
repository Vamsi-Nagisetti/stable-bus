from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class PaymentGatewayAdapter(ABC):

    @abstractmethod
    def create_order(
        self,
        order_id: str,
        amount: Decimal,
        customer: dict[str, Any],
        idempotency_key: str,
        currency: str = "INR",
        return_url: str | None = None
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def verify_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def get_payment_status(
        self,
        payment_reference: str
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def refund_payment(
        self,
        payment_reference: str,
        amount: Decimal,
        refund_id: str,
        idempotency_key: str
    ) -> dict[str, Any]:
        pass

    def get_refund_status(
        self,
        refund_id: str
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Refund status lookup is not supported by this provider"
        )

    def get_refunds_for_payment(
        self,
        payment_reference: str,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Refund listing is not supported by this provider"
        )

    def get_payments_for_order(
    self,
        order_id: str,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Payment listing by order is not supported by this provider"
        )
    @abstractmethod
    def close(self) -> None:
        pass