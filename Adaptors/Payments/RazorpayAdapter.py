
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
            self.key_secret
        )
        self.session.headers.update({
            "Content-Type": "application/json"
        })

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"

        response = self.session.request(
            method=method,
            url=url,
            timeout=20,
            **kwargs
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
        except InvalidOperation:
            raise ValueError("Invalid payment amount.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError("Amount must be a positive finite value.")

        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError("Amount cannot have more than 2 decimal places.")

        return int(amount * 100)

    def create_order(
        self,
        order_id: str,
        amount: Decimal,
        customer: dict[str, Any],
        idempotency_key: str,
        currency: str = "INR",
        return_url: str | None = None
    ) -> dict[str, Any]:

        payload = {
            "amount": self._convert_to_paise(amount),
            "currency": currency,
            "receipt": order_id
        }

        return self._request(
            "POST",
            "/orders",
            json=payload
        )

    def verify_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str
    ) -> dict[str, Any]:

        if not all([order_id, payment_id, signature]):
            raise ValueError("Payment verification parameters are missing.")

        message = f"{order_id}|{payment_id}"

        expected_signature = hmac.new(
            self.key_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        signature_valid = hmac.compare_digest(
            expected_signature,
            signature
        )

        if not signature_valid:
            return {
                "verified": False,
                "message": "Invalid payment signature."
            }

        payment = self._request(
            "GET",
            f"/payments/{payment_id}"
        )

        if payment.get("order_id") != order_id:
            return {
                "verified": False,
                "message": "Payment order ID mismatch."
            }

        return {
            "verified": True,
            "payment_id": payment.get("id"),
            "order_id": payment.get("order_id"),
            "amount": payment.get("amount"),
            "currency": payment.get("currency"),
            "status": payment.get("status"),
            "captured": payment.get("captured", False)
        }

    def get_payment_status(
        self,
        payment_reference: str
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            f"/payments/{payment_reference}"
        )

    
    def refund_payment(
        self,
        payment_reference: str,
        amount: Decimal,
        refund_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:

        if amount <= Decimal("0"):
            raise ValueError("Refund amount must be greater than zero")

        amount_paise = int(amount * 100)

        payload = {
            "amount": amount_paise,
            "receipt": refund_id,
        }

        response = requests.post(
            f"{self.base_url}/payments/{payment_reference}/refund",
            json=payload,
            auth=(self.key_id, self.key_secret),
            timeout=30,
        )

        response.raise_for_status()

        refund_data = response.json()

        return {
            "id": refund_data["id"],
            "payment_id": refund_data["payment_id"],
            "amount": refund_data["amount"],
            "currency": refund_data["currency"],
            "status": refund_data["status"],
        }

    def close(self) -> None:
        self.session.close()
