
import os
import requests

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

from Strategies.Payments.PaymentStrategy import PaymentStrategy


class CashFreePayment(PaymentStrategy):

    def __init__(self):

        self.client_id = os.getenv("CASHFREE_CLIENT_ID")
        self.client_secret = os.getenv("CASHFREE_CLIENT_SECRET")

        self.environment = os.getenv(
            "CASHFREE_ENV", "sandbox"
        ).lower()

        self.api_version = os.getenv(
            "CASHFREE_API_VERSION", "2023-08-01"
        )

        if not self.client_id or not self.client_secret:
            raise ValueError("Cashfree credentials are missing.")

        if self.environment == "production":
            self.base_url = "https://api.cashfree.com/pg"
        else:
            self.base_url = "https://sandbox.cashfree.com/pg"

        self.session = requests.Session()

        self.session.headers.update({
            "Content-Type": "application/json",
            "x-client-id": self.client_id,
            "x-client-secret": self.client_secret,
            "x-api-version": self.api_version,
        })

    # --------------------------------------------------
    # COMMON API REQUEST HANDLER
    # --------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        idempotency_key: str | None = None,
        **kwargs,
    ) -> Any:

        headers = kwargs.pop("headers", {}).copy()

        if idempotency_key:
            headers["x-idempotency-key"] = idempotency_key

        response = self.session.request(
            method,
            f"{self.base_url}{endpoint}",
            timeout=20,
            headers=headers,
            **kwargs,
        )

        if not response.ok:
            raise RuntimeError(
                f"Cashfree API Error: "
                f"HTTP {response.status_code} - {response.text}"
            )

        if not response.content:
            return {}

        return response.json()

    # --------------------------------------------------
    # AMOUNT VALIDATION
    # --------------------------------------------------

    @staticmethod
    def _validate_amount(amount: Decimal) -> Decimal:

        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise ValueError("Invalid payment amount")

        if not amount.is_finite() or amount <= 0:
            raise ValueError("Payment amount must be positive")

        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError(
                "Amount cannot have more than 2 decimal places"
            )

        return amount

    # --------------------------------------------------
    # CREATE PAYMENT ORDER
    # --------------------------------------------------

    def create_order(
        self,
        order_id: str,
        amount: Decimal,
        customer: dict[str, Any],
        idempotency_key: str,
        currency: str = "INR",
        return_url: str | None = None,
    ) -> dict[str, Any]:

        if not idempotency_key:
            raise ValueError("Idempotency key is required")

        amount = self._validate_amount(amount)

        customer_details = {
            "customer_id": str(
                customer.get("customer_id")
                or customer.get("id")
                or order_id
            ),
            "customer_phone": customer.get("phone"),
        }

        if customer.get("email"):
            customer_details["customer_email"] = customer["email"]

        if not customer_details["customer_phone"]:
            raise ValueError(
                "Customer phone number is required by Cashfree"
            )

        payload = {
            "order_id": order_id,
            "order_amount": float(amount),
            "order_currency": currency,
            "customer_details": customer_details,
        }

        if return_url:
            payload["order_meta"] = {
                "return_url": return_url
            }

        response = self._request(
            "POST",
            "/orders",
            idempotency_key=idempotency_key,
            json=payload,
        )

        # Normalize the response to match Razorpay's
        # create_order response convention.
        return {
            **response,
            "id": response.get("order_id"),
            "payment_session_id": response.get(
                "payment_session_id"
            ),
        }

    # --------------------------------------------------
    # VERIFY PAYMENT
    # --------------------------------------------------

    def verify_payment(self, **kwargs) -> dict[str, Any]:

        order_id = kwargs["order_id"]
        payment_id = kwargs.get("payment_id")

        if payment_id:
            endpoint = (
                f"/orders/{quote(str(order_id), safe='')}"
                f"/payments/{quote(str(payment_id), safe='')}"
            )

            payment_details = self._request(
                "GET",
                endpoint,
            )

        else:
            payments = self._request(
                "GET",
                f"/orders/{quote(str(order_id), safe='')}/payments",
            )

            if not payments:
                return {
                    "verified": False,
                    "status": "pending",
                    "message": "No payment attempt found",
                }

            # Prefer a successful payment if multiple
            # payment attempts exist for this order.
            payment_details = next(
                (
                    item for item in payments
                    if item.get("payment_status") == "SUCCESS"
                ),
                payments[0],
            )

        if str(payment_details.get("order_id")) != str(order_id):
            return {
                "verified": False,
                "status": "FAILED",
                "message": "Payment order mismatch",
            }

        payment_status = payment_details.get("payment_status")

        captured = (
            payment_status == "SUCCESS"
            and payment_details.get("is_captured") is True
        )

        status = (
            "captured"
            if captured
            else (payment_status or "PENDING").lower()
        )

        amount = payment_details.get("payment_amount")

        if amount is None:
            amount = payment_details.get("order_amount")

        amount_in_paise = (
            int(Decimal(str(amount)) * 100)
            if amount is not None
            else None
        )

        return {
            "verified": True,
            "status": status,
            "payment_id": str(
                payment_details.get("cf_payment_id")
            ),
            "order_id": payment_details.get("order_id"),
            "amount": amount_in_paise,
            "currency": payment_details.get("payment_currency"),
            "captured": captured,
        }

    # --------------------------------------------------
    # GET PAYMENT STATUS
    # --------------------------------------------------

    def get_payment_status(
        self,
        payment_reference: str,
    ) -> dict[str, Any]:

        order_id = quote(str(payment_reference), safe="")

        payments = self._request(
            "GET",
            f"/orders/{order_id}/payments",
        )

        if not payments:
            return {
                "status": "pending",
                "payments": [],
            }

        selected_payment = next(
            (
                item for item in payments
                if item.get("payment_status") == "SUCCESS"
            ),
            payments[0],
        )

        return self.verify_payment(
            order_id=payment_reference,
            payment_id=selected_payment.get("cf_payment_id"),
        )

    # --------------------------------------------------
    # REFUND PAYMENT
    # --------------------------------------------------

    def refund_payment(
        self,
        payment_reference: str,
        amount: Decimal,
        refund_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:

        if not idempotency_key:
            raise ValueError("Refund idempotency key is required")

        amount = self._validate_amount(amount)

        payload = {
            "refund_amount": float(amount),
            "refund_id": refund_id,
            "refund_note": "StableBus customer refund",
        }

        order_id = quote(str(payment_reference), safe="")

        return self._request(
            "POST",
            f"/orders/{order_id}/refunds",
            idempotency_key=idempotency_key,
            json=payload,
        )

    # --------------------------------------------------
    # CLOSE HTTP SESSION
    # --------------------------------------------------

    def close(self):
        self.session.close()
