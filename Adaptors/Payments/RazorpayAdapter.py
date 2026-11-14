
import os
import hmac
import hashlib
import requests

from decimal import Decimal, InvalidOperation
from typing import Any
from requests.auth import HTTPBasicAuth

from Adaptors.Payments.PaymentGatewayAdapter import PaymentGatewayAdapter


class RazorpayAdapter(PaymentGatewayAdapter):

    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET")

        if not self.key_id or not self.key_secret:
            raise ValueError("Razorpay credentials are missing.")

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(
            self.key_id,
            self.key_secret,
        )
        self.session.headers.update({
            "Content-Type": "application/json",
        })

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"

        response = self.session.request(
            method=method,
            url=url,
            timeout=30,
            **kwargs,
        )

        if not response.ok:
            raise RuntimeError(
                f"Razorpay API error {response.status_code}: "
                f"{response.text}"
            )

        return response.json()

    @staticmethod
    def _convert_to_paise(amount: Decimal) -> int:
        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid payment amount.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError(
                "Amount must be a positive finite value."
            )

        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError(
                "Amount cannot have more than 2 decimal places."
            )

        return int(amount * 100)

    def create_order(
        self,
        order_id: str,
        amount: Decimal,
        customer: dict[str, Any],
        idempotency_key: str,
        currency: str = "INR",
        return_url: str | None = None,
    ) -> dict[str, Any]:

        if not order_id:
            raise ValueError("Order ID is required.")

        payload = {
            "amount": self._convert_to_paise(amount),
            "currency": currency,
            "receipt": order_id,
        }

        return self._request(
            "POST",
            "/orders",
            json=payload,
        )

    def verify_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> dict[str, Any]:

        if not all([order_id, payment_id, signature]):
            raise ValueError(
                "Payment verification parameters are missing."
            )

        message = f"{order_id}|{payment_id}"

        expected_signature = hmac.new(
            self.key_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        signature_valid = hmac.compare_digest(
            expected_signature,
            signature,
        )

        if not signature_valid:
            return {
                "verified": False,
                "message": "Invalid payment signature.",
            }

        payment = self._request(
            "GET",
            f"/payments/{payment_id}",
        )

        if payment.get("order_id") != order_id:
            return {
                "verified": False,
                "message": "Payment order ID mismatch.",
            }

        return {
            "verified": True,
            "payment_id": payment.get("id"),
            "order_id": payment.get("order_id"),
            "amount": payment.get("amount"),
            "currency": payment.get("currency"),
            "status": payment.get("status"),
            "captured": payment.get("captured", False),
        }

    def get_payment_status(
        self,
        payment_reference: str,
    ) -> dict[str, Any]:

        if not payment_reference:
            raise ValueError("Gateway payment ID is required.")

        return self._request(
            "GET",
            f"/payments/{payment_reference}",
        )

    def refund_payment(
        self,
        payment_reference: str,
        amount: Decimal,
        refund_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:

        if not payment_reference:
            raise ValueError("Gateway payment ID is required.")

        if not refund_id:
            raise ValueError("StableBus refund ID is required.")

        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("Refund idempotency key is required.")

        payload = {
            "amount": self._convert_to_paise(amount),
            "receipt": refund_id,
        }

        # Use the authenticated session consistently.
        # StableBus refund ID is sent as Razorpay receipt
        # so an uncertain response can be reconciled later.
        refund_data = self._request(
            "POST",
            f"/payments/{payment_reference}/refund",
            json=payload,
        )

        return {
            "id": refund_data.get("id"),
            "payment_id": refund_data.get("payment_id"),
            "amount": refund_data.get("amount"),
            "currency": refund_data.get("currency"),
            "status": refund_data.get("status"),
            "receipt": refund_data.get("receipt"),
        }

    def get_refund_status(
        self,
        refund_id: str,
    ) -> dict[str, Any]:

        if not refund_id:
            raise ValueError("Gateway refund ID is required.")

        # refund_id here must be the Razorpay refund ID,
        # not the StableBus internal refund ID.
        return self._request(
            "GET",
            f"/refunds/{refund_id}",
        )

    def get_refunds_for_payment(
        self,
        payment_reference: str,
    ) -> list[dict[str, Any]]:

        if not payment_reference:
            raise ValueError("Gateway payment ID is required.")

        response = self._request(
            "GET",
            f"/payments/{payment_reference}/refunds",
        )

        if not isinstance(response, dict):
            raise ValueError("Invalid Razorpay refund-list response")

        items = response.get("items", [])

        if not isinstance(items, list):
            raise ValueError("Invalid Razorpay refund-list items")

        return items

    def get_payments_for_order(
        self,
        order_id: str,
    ) -> list[dict[str, Any]]:

        if not order_id:
            raise ValueError("Gateway order ID is required.")

        response = self._request(
            "GET",
            f"/orders/{order_id}/payments",
        )

        if not isinstance(response, dict):
            raise ValueError("Invalid Razorpay payment-list response")

        items = response.get("items", [])

        if not isinstance(items, list):
            raise ValueError("Invalid Razorpay payment-list items")

        return items
    def close(self) -> None:
        self.session.close()
