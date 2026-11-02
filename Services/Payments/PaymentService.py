
from decimal import Decimal
from uuid import uuid4
from typing import Any

from Services.Payments.PaymentsServiceInterface import (
    PaymentServiceInterface,
)

from models.Payment import Payment
from models.Refund import Refund


class PaymentService(PaymentServiceInterface):

    def __init__(
        self,
        payment_provider,
        payment_repository,
        booking_repository,
        payment_cache_repository,
        refund_repository,
        gateway_name: str = "RAZORPAY",
    ):
        self.payment_provider = payment_provider
        self.payment_repository = payment_repository
        self.booking_repository = booking_repository
        self.payment_cache_repository = payment_cache_repository
        self.refund_repository = refund_repository
        self.gateway_name = gateway_name

    @property
    def database(self):
        return self.payment_repository.database

    def initiate_payment(
        self,
        booking_id: str,
        idempotency_key: str,
        customer: dict[str, Any],
    ) -> dict[str, Any]:

        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("Idempotency key is required")

        existing_payment = (
            self.payment_repository.get_by_idempotency_key(
                idempotency_key
            )
        )

        if existing_payment:
            if existing_payment.booking_id != booking_id:
                raise ValueError(
                    "Idempotency key already belongs to another booking"
                )

            return self._payment_response(
                existing_payment,
                existing_attempt=True,
            )

        booking = self.booking_repository.get_by_id(booking_id)

        if not booking:
            raise ValueError("Booking not found")

        amount = Decimal(str(booking.total_amount))

        if not amount.is_finite() or amount <= Decimal("0"):
            raise ValueError("Invalid booking amount")

        payment = Payment(
            booking_id=booking.id,
            payment_attempt_id=str(uuid4()),
            gateway=self.gateway_name,
            amount=amount,
            currency=booking.currency,
            status="PROCESSING",
            idempotency_key=idempotency_key,
        )

        try:
            self.payment_repository.create(payment)
            self.database.commit()
            self.database.refresh(payment)

        except Exception:
            self.database.rollback()

            existing_payment = (
                self.payment_repository.get_by_idempotency_key(
                    idempotency_key
                )
            )

            if existing_payment:
                if existing_payment.booking_id != booking_id:
                    raise ValueError(
                        "Idempotency key already belongs to another booking"
                    )

                return self._payment_response(
                    existing_payment,
                    existing_attempt=True,
                )

            raise

        try:
            gateway_response = self.payment_provider.create_order(
                order_id=payment.payment_attempt_id,
                amount=amount,
                customer=customer,
                idempotency_key=idempotency_key,
                currency=payment.currency,
            )

            gateway_order_id = gateway_response.get("id")

            if not gateway_order_id:
                raise ValueError(
                    "Gateway did not return an order ID"
                )

        except Exception:
            self.database.rollback()

            payment = self.payment_repository.get_by_id(payment.id)

            if payment:
                payment.status = "UNKNOWN"
                self.database.commit()
                self.database.refresh(payment)

                self._invalidate_payment_cache(payment.id)

            return self._payment_response(payment)

        payment = self.payment_repository.get_by_id(payment.id)

        payment.gateway_order_id = gateway_order_id
        payment.status = "PENDING"

        self.database.commit()
        self.database.refresh(payment)

        self._invalidate_payment_cache(payment.id)

        return self._payment_response(payment)

    def verify_payment(
        self,
        payment_id: str,
        gateway_payment_id: str,
        signature: str,
    ) -> dict[str, Any]:

        payment = self.payment_repository.get_by_id(payment_id)

        if not payment:
            raise ValueError("Payment record not found")

        if payment.status == "SUCCESS":
            return {
                "payment_id": payment.id,
                "status": "SUCCESS",
                "message": "Payment already verified",
            }

        if payment.status not in ("PENDING", "UNKNOWN"):
            raise ValueError(
                f"Payment cannot be verified in status: {payment.status}"
            )

        if not payment.gateway_order_id:
            raise ValueError("Gateway order ID is missing")

        result = self.payment_provider.verify_payment(
            order_id=payment.gateway_order_id,
            payment_id=gateway_payment_id,
            signature=signature,
        )

        if not result.get("verified"):
            raise ValueError("Payment verification failed")

        if result.get("payment_id") != gateway_payment_id:
            raise ValueError("Gateway payment ID mismatch")

        if result.get("order_id") != payment.gateway_order_id:
            raise ValueError("Gateway order ID mismatch")

        expected_amount = int(payment.amount * 100)

        if result.get("amount") != expected_amount:
            raise ValueError("Payment amount mismatch")

        if result.get("currency") != payment.currency:
            raise ValueError("Payment currency mismatch")

        if result.get("status") != "captured":
            return {
                "payment_id": payment.id,
                "status": result.get("status"),
                "message": "Payment is not captured yet",
            }

        try:
            self.payment_repository.update_status(
                payment.id,
                "SUCCESS",
                gateway_payment_id,
            )

            self.database.commit()
            self._invalidate_payment_cache(payment.id)

        except Exception:
            self.database.rollback()
            raise

        return {
            "payment_id": payment.id,
            "gateway_payment_id": gateway_payment_id,
            "status": "SUCCESS",
            "message": "Payment verified successfully",
        }

    def get_payment_status(
        self,
        payment_id: str,
    ) -> dict[str, Any]:

        try:
            cached_payment = (
                self.payment_cache_repository.get_payment_status(
                    payment_id
                )
            )

            if cached_payment is not None:
                cached_payment["cache_hit"] = True
                return cached_payment

        except Exception:
            pass

        payment = self.payment_repository.get_by_id(payment_id)

        if not payment:
            raise ValueError("Payment record not found")

        payment_data = {
            "payment_id": payment.id,
            "booking_id": payment.booking_id,
            "gateway": payment.gateway,
            "gateway_order_id": payment.gateway_order_id,
            "gateway_payment_id": payment.gateway_payment_id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "status": payment.status,
        }

        try:
            self.payment_cache_repository.set_payment_status(
                payment.id,
                payment_data,
            )

        except Exception:
            pass

        payment_data["cache_hit"] = False

        return payment_data

    def refund_payment(
        self,
        payment_id: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> dict[str, Any]:

        # 1. Validate the request.
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("Refund idempotency key is required")

        amount = Decimal(str(amount))

        if not amount.is_finite() or amount <= Decimal("0"):
            raise ValueError("Refund amount must be greater than zero")

        # 2. Check whether this refund request already exists.
        existing_refund = (
            self.refund_repository.get_by_idempotency_key(
                idempotency_key
            )
        )

        if existing_refund:
            if existing_refund.payment_id != payment_id:
                raise ValueError(
                    "Idempotency key already belongs to another payment"
                )

            return self._refund_response(
                existing_refund,
                existing_attempt=True,
            )

        try:
            # 3. Lock the payment row to prevent concurrent over-refunds.
            payment = self.payment_repository.get_by_id_for_update(
                payment_id
            )

            if not payment:
                raise ValueError("Payment record not found")

            # Check again after acquiring the lock.
            existing_refund = (
                self.refund_repository.get_by_idempotency_key(
                    idempotency_key
                )
            )

            if existing_refund:
                if existing_refund.payment_id != payment_id:
                    raise ValueError(
                        "Idempotency key already belongs to another payment"
                    )

                self.database.rollback()

                return self._refund_response(
                    existing_refund,
                    existing_attempt=True,
                )

            # 4. Only successfully captured payments can be refunded.
            if payment.status != "SUCCESS":
                raise ValueError(
                    "Only successful payments can be refunded"
                )

            if not payment.gateway_payment_id:
                raise ValueError("Gateway payment ID is missing")

            if amount > payment.amount:
                raise ValueError(
                    "Refund amount exceeds original payment amount"
                )

            # 5. Calculate the remaining refundable amount.
            already_refunded = Decimal(
                str(
                    self.refund_repository.get_total_refunded_amount(
                        payment_id
                    )
                )
            )

            remaining_amount = payment.amount - already_refunded

            if amount > remaining_amount:
                raise ValueError(
                    f"Refund exceeds remaining refundable amount: "
                    f"{remaining_amount}"
                )

            # 6. Create a durable refund record before calling the gateway.
            refund = Refund(
                payment_id=payment.id,
                amount=amount,
                currency=payment.currency,
                status="PROCESSING",
                idempotency_key=idempotency_key,
            )

            self.refund_repository.create(refund)

            self.database.commit()
            self.database.refresh(refund)

        except Exception:
            self.database.rollback()

            existing_refund = (
                self.refund_repository.get_by_idempotency_key(
                    idempotency_key
                )
            )

            if existing_refund:
                if existing_refund.payment_id != payment_id:
                    raise ValueError(
                        "Idempotency key already belongs to another payment"
                    )

                return self._refund_response(
                    existing_refund,
                    existing_attempt=True,
                )

            raise

        # 7. Send the refund request to the payment gateway.
        try:
            gateway_response = self.payment_provider.refund_payment(
                payment_reference=payment.gateway_payment_id,
                amount=amount,
                refund_id=refund.id,
                idempotency_key=idempotency_key,
            )

            gateway_refund_id = gateway_response.get("id")
            gateway_status = gateway_response.get("status")

            if not gateway_refund_id or not gateway_status:
                raise ValueError(
                    "Gateway returned an incomplete refund response"
                )

            # 8. Map gateway status to StableBus status.
            status_mapping = {
                "processed": "SUCCESS",
                "pending": "PROCESSING",
                "failed": "FAILED",
            }

            refund_status = status_mapping.get(
                gateway_status.lower(),
                "UNKNOWN",
            )

            self.refund_repository.update_status(
                refund.id,
                refund_status,
                gateway_refund_id,
            )

            self.database.commit()

        except Exception:
            # The gateway may have received the request even if
            # StableBus did not receive its response.
            self.database.rollback()

            refund = self.refund_repository.get_by_id(refund.id)

            if refund:
                refund.status = "UNKNOWN"
                self.database.commit()

            return self._refund_response(refund)

        refund = self.refund_repository.get_by_id(refund.id)

        return self._refund_response(refund)

    def _invalidate_payment_cache(self, payment_id: str) -> None:

        try:
            self.payment_cache_repository.invalidate_payment_status(
                payment_id
            )

        except Exception:
            pass

    @staticmethod
    def _payment_response(
        payment,
        existing_attempt: bool = False,
    ) -> dict[str, Any]:

        if payment is None:
            return {
                "status": "UNKNOWN",
                "message": "Payment outcome requires reconciliation",
            }

        return {
            "payment_id": payment.id,
            "payment_attempt_id": payment.payment_attempt_id,
            "gateway_order_id": payment.gateway_order_id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "status": payment.status,
            "existing_attempt": existing_attempt,
        }

    @staticmethod
    def _refund_response(
        refund,
        existing_attempt: bool = False,
    ) -> dict[str, Any]:

        if refund is None:
            return {
                "status": "UNKNOWN",
                "message": "Refund outcome requires reconciliation",
            }

        return {
            "refund_id": refund.id,
            "payment_id": refund.payment_id,
            "gateway_refund_id": refund.gateway_refund_id,
            "amount": str(refund.amount),
            "currency": refund.currency,
            "status": refund.status,
            "existing_attempt": existing_attempt,
        }
