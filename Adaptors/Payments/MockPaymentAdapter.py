
from decimal import Decimal
from typing import Any
from uuid import uuid4

from Adaptors.Payments.PaymentGatewayAdapter import PaymentGatewayAdapter


class MockPaymentAdapter(PaymentGatewayAdapter):

    EXPECTED_SIGNATURE = "mock-signature"

    def __init__(self):
        self.orders = {}
        self.payments = {}
        self.refunds = {}

        # Default refund behavior
        self.next_refund_behavior = "success"

    # =====================================================
    # PAYMENT ORDER
    # =====================================================

    def create_order(
        self,
        order_id: str,
        amount: Decimal,
        customer: dict[str, Any],
        idempotency_key: str,
        currency: str = "INR",
        return_url: str | None = None,
    ) -> dict[str, Any]:

        gateway_order_id = f"mock_order_{uuid4().hex[:12]}"

        self.orders[gateway_order_id] = {
            "id": gateway_order_id,
            "receipt": order_id,
            "amount": int(amount * 100),
            "currency": currency,
            "status": "created",
        }

        return self.orders[gateway_order_id]

    # =====================================================
    # PAYMENT VERIFICATION
    # =====================================================

    def verify_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> dict[str, Any]:

        payment = self.payments.get(payment_id)

        if not payment:
            return {
                "verified": False,
                "message": "Mock payment not found",
            }

        if payment["order_id"] != order_id:
            return {
                "verified": False,
                "message": "Order ID mismatch",
            }

        if signature != self.EXPECTED_SIGNATURE:
            return {
                "verified": False,
                "message": "Invalid payment signature",
            }

        return {
            "verified": True,
            "payment_id": payment_id,
            "order_id": order_id,
            "amount": payment["amount"],
            "currency": payment["currency"],
            "status": payment["status"],
            "captured": payment["status"] == "captured",
        }

    # =====================================================
    # PAYMENT STATUS
    # =====================================================

    def get_payment_status(
        self,
        payment_reference: str,
    ) -> dict[str, Any]:

        payment = self.payments.get(payment_reference)

        if not payment:
            raise ValueError("Mock payment not found")

        return payment

    # =====================================================
    # REFUND SIMULATION CONTROLS
    # =====================================================

    def simulate_refund_failure(self):
        """Simulate a refund rejected by the gateway."""
        self.next_refund_behavior = "failed"

    def simulate_refund_timeout(self):
        """
        Simulate gateway processing the refund,
        but StableBus not receiving the response.
        """
        self.next_refund_behavior = "timeout"

    def simulate_incomplete_refund_response(self):
        """Simulate a gateway returning incomplete data."""
        self.next_refund_behavior = "incomplete"

    def simulate_successful_refund(self):
        """Set the next refund to succeed."""
        self.next_refund_behavior = "success"

    # =====================================================
    # INTERNAL REFUND CREATION
    # =====================================================

    def _create_mock_refund(
        self,
        payment_reference: str,
        amount: Decimal,
        refund_id: str,
        idempotency_key: str,
        status: str,
    ) -> dict[str, Any]:

        payment = self.payments.get(payment_reference)

        if not payment:
            raise ValueError("Mock payment not found")

        amount_paise = int(amount * 100)

        if amount_paise <= 0:
            raise ValueError("Refund amount must be greater than zero")

        already_refunded = sum(
            refund["amount"]
            for refund in self.refunds.values()
            if refund["payment_id"] == payment_reference
            and refund["status"] in ("processed", "pending")
        )

        refundable_amount = payment["amount"] - already_refunded

        if amount_paise > refundable_amount:
            raise ValueError("Refund amount exceeds refundable amount")

        refund = {
            "id": f"mock_refund_{uuid4().hex[:12]}",
            "payment_id": payment_reference,
            "refund_id": refund_id,
            "amount": amount_paise,
            "currency": payment["currency"],
            "status": status,
            "idempotency_key": idempotency_key,
        }

        self.refunds[refund_id] = refund

        return refund

    # =====================================================
    # REFUND PAYMENT
    # =====================================================

    def refund_payment(
        self,
        payment_reference: str,
        amount: Decimal,
        refund_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:

        # Idempotent gateway response.
        if refund_id in self.refunds:
            return self.refunds[refund_id]

        payment = self.payments.get(payment_reference)

        if not payment:
            raise ValueError("Mock payment not found")

        if payment["status"] != "captured":
            raise ValueError("Only captured payments can be refunded")

        behavior = self.next_refund_behavior

        # Reset behavior after consuming it.
        self.next_refund_behavior = "success"

        # Gateway rejects refund.
        if behavior == "failed":

            return self._create_mock_refund(
                payment_reference,
                amount,
                refund_id,
                idempotency_key,
                "failed",
            )

        # Gateway processes refund but response is lost.
        if behavior == "timeout":

            self._create_mock_refund(
                payment_reference,
                amount,
                refund_id,
                idempotency_key,
                "processed",
            )

            raise TimeoutError("Mock gateway refund timeout")

        # Gateway processes refund but returns incomplete response.
        if behavior == "incomplete":

            self._create_mock_refund(
                payment_reference,
                amount,
                refund_id,
                idempotency_key,
                "processed",
            )

            return {
                "status": "processed",
            }

        # Normal successful refund.
        return self._create_mock_refund(
            payment_reference,
            amount,
            refund_id,
            idempotency_key,
            "processed",
        )

    # =====================================================
    # REFUND STATUS LOOKUP
    # =====================================================

    def get_refund_status(
        self,
        refund_id: str,
    ) -> dict[str, Any]:

        refund = self.refunds.get(refund_id)

        if not refund:
            raise ValueError("Mock refund not found")

        return refund

    # =====================================================
    # PAYMENT SIMULATION
    # =====================================================

    def simulate_successful_payment(
        self,
        gateway_order_id: str,
    ) -> str:

        order = self.orders.get(gateway_order_id)

        if not order:
            raise ValueError("Mock order not found")

        payment_id = f"mock_pay_{uuid4().hex[:12]}"

        self.payments[payment_id] = {
            "id": payment_id,
            "order_id": gateway_order_id,
            "amount": order["amount"],
            "currency": order["currency"],
            "status": "captured",
            "captured": True,
        }

        return payment_id

    def simulate_failed_payment(
        self,
        gateway_order_id: str,
    ) -> str:

        order = self.orders.get(gateway_order_id)

        if not order:
            raise ValueError("Mock order not found")

        payment_id = f"mock_pay_{uuid4().hex[:12]}"

        self.payments[payment_id] = {
            "id": payment_id,
            "order_id": gateway_order_id,
            "amount": order["amount"],
            "currency": order["currency"],
            "status": "failed",
            "captured": False,
        }

        return payment_id

    def close(self) -> None:
        pass
