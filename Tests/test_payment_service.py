
"""
StableBus PaymentService unit tests.

Run:
    python .\test_payment_service.py

Uses in-memory fake repositories and cache.
No real database, Redis, or payment gateway calls.
"""

import sys
import unittest

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Services.Payments.PaymentService import PaymentService
from Adaptors.Payments.MockPaymentAdapter import MockPaymentAdapter


# =========================================================
# FAKE DATABASE
# =========================================================

class FakeDatabase:

    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, instance):
        return instance


# =========================================================
# FAKE PAYMENT REPOSITORY
# =========================================================

class FakePaymentRepository:

    def __init__(self, database):
        self.database = database
        self.payments = {}

    def create(self, payment):
        if not payment.id:
            payment.id = str(uuid4())

        self.payments[payment.id] = payment
        return payment

    def get_by_id(self, payment_id):
        return self.payments.get(payment_id)

    def get_by_idempotency_key(self, key):
        for payment in self.payments.values():
            if payment.idempotency_key == key:
                return payment
        return None

    def update_status(
        self,
        payment_id,
        status,
        gateway_payment_id=None,
    ):
        payment = self.get_by_id(payment_id)

        if payment is None:
            return None

        payment.status = status

        if gateway_payment_id:
            payment.gateway_payment_id = gateway_payment_id

        return payment

    def get_by_id_for_update(self, payment_id):
        return self.get_by_id(payment_id)


# =========================================================
# FAKE REFUND REPOSITORY
# =========================================================

class FakeRefundRepository:

    RESERVED_STATUSES = {
        "PENDING",
        "PROCESSING",
        "UNKNOWN",
        "SUCCESS",
    }

    def __init__(self, database):
        self.database = database
        self.refunds = {}

    def create(self, refund):
        if not refund.id:
            refund.id = str(uuid4())

        self.refunds[refund.id] = refund
        return refund

    def get_by_id(self, refund_id):
        return self.refunds.get(refund_id)

    def get_by_idempotency_key(self, key):
        for refund in self.refunds.values():
            if refund.idempotency_key == key:
                return refund
        return None

    def get_by_payment_id(self, payment_id):
        return [
            refund
            for refund in self.refunds.values()
            if refund.payment_id == payment_id
        ]

    def get_total_refunded_amount(self, payment_id):
        return sum(
            (
                refund.amount
                for refund in self.refunds.values()
                if refund.payment_id == payment_id
                and refund.status in self.RESERVED_STATUSES
            ),
            Decimal("0.00"),
        )

    def update_status(
        self,
        refund_id,
        status,
        gateway_refund_id=None,
    ):
        refund = self.get_by_id(refund_id)

        if refund is None:
            return None

        refund.status = status

        if gateway_refund_id:
            refund.gateway_refund_id = gateway_refund_id

        return refund


# =========================================================
# FAKE BOOKING REPOSITORY
# =========================================================

class FakeBookingRepository:

    def __init__(self):
        self.bookings = {}

    def add_booking(
        self,
        amount=Decimal("735.00"),
        currency="INR",
    ):
        booking_id = str(uuid4())

        self.bookings[booking_id] = SimpleNamespace(
            id=booking_id,
            total_amount=amount,
            currency=currency,
        )

        return booking_id

    def get_by_id(self, booking_id):
        return self.bookings.get(booking_id)


# =========================================================
# FAKE CACHE
# =========================================================

class FakePaymentCacheRepository:

    def __init__(self):
        self.cache = {}

    def get_payment_status(self, payment_id):
        cached = self.cache.get(payment_id)
        return dict(cached) if cached is not None else None

    def set_payment_status(self, payment_id, data):
        self.cache[payment_id] = dict(data)

    def invalidate_payment_status(self, payment_id):
        self.cache.pop(payment_id, None)


# =========================================================
# TEST CASES
# =========================================================

class PaymentServiceTestCase(unittest.TestCase):

    def setUp(self):

        self.database = FakeDatabase()

        self.payment_repository = FakePaymentRepository(
            self.database
        )

        self.refund_repository = FakeRefundRepository(
            self.database
        )

        self.booking_repository = FakeBookingRepository()

        self.payment_cache_repository = FakePaymentCacheRepository()

        self.payment_provider = MockPaymentAdapter()

        self.service = PaymentService(
            payment_provider=self.payment_provider,
            payment_repository=self.payment_repository,
            booking_repository=self.booking_repository,
            payment_cache_repository=self.payment_cache_repository,
            refund_repository=self.refund_repository,
            gateway_name="MOCK",
        )

        self.customer = {
            "name": "StableBus Test Customer",
            "email": "test@stablebus.com",
            "contact": "9999999999",
        }

    def tearDown(self):
        self.payment_provider.close()

    def create_booking(self):
        return self.booking_repository.add_booking(
            amount=Decimal("735.00"),
            currency="INR",
        )

    def create_successful_payment(self):

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id=booking_id,
            idempotency_key=f"payment-{uuid4()}",
            customer=self.customer,
        )

        gateway_payment_id = (
            self.payment_provider.simulate_successful_payment(
                response["gateway_order_id"]
            )
        )

        result = self.service.verify_payment(
            payment_id=response["payment_id"],
            gateway_payment_id=gateway_payment_id,
            signature="mock-signature",
        )

        self.assertEqual(result["status"], "SUCCESS")

        return response["payment_id"]

    # =====================================================
    # TEST 1: PAYMENT IDEMPOTENCY
    # =====================================================

    def test_payment_idempotency(self):

        print("\n[TEST] Payment idempotency")

        booking_id = self.create_booking()
        key = f"idem-{uuid4()}"

        first = self.service.initiate_payment(
            booking_id, key, self.customer
        )

        self.assertEqual(first["status"], "PENDING")
        self.assertFalse(first["existing_attempt"])

        second = self.service.initiate_payment(
            booking_id, key, self.customer
        )

        self.assertEqual(first["payment_id"], second["payment_id"])
        self.assertTrue(second["existing_attempt"])

        another_booking = self.create_booking()

        with self.assertRaisesRegex(
            ValueError,
            "Idempotency key already belongs to another booking",
        ):
            self.service.initiate_payment(
                another_booking, key, self.customer
            )

        third = self.service.initiate_payment(
            booking_id, f"idem-{uuid4()}", self.customer
        )

        self.assertNotEqual(first["payment_id"], third["payment_id"])

        print("PASS: Same key returns the same attempt.")
        print("PASS: Same key cannot be reused for another booking.")
        print("PASS: New key creates a new attempt.")

    # =====================================================
    # TEST 2: PAYMENT STATUS CACHE
    # =====================================================

    def test_payment_status_cache(self):

        print("\n[TEST] Payment status cache")

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id, f"cache-{uuid4()}", self.customer
        )

        payment_id = response["payment_id"]

        first = self.service.get_payment_status(payment_id)
        second = self.service.get_payment_status(payment_id)

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])

        print("PASS: First read is a cache miss.")
        print("PASS: Second read is a cache hit.")

    # =====================================================
    # TEST 3: SUCCESSFUL PAYMENT VERIFICATION
    # =====================================================

    def test_payment_verification(self):

        print("\n[TEST] Payment verification")

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id, f"verify-{uuid4()}", self.customer
        )

        payment_id = response["payment_id"]

        gateway_payment_id = (
            self.payment_provider.simulate_successful_payment(
                response["gateway_order_id"]
            )
        )

        result = self.service.verify_payment(
            payment_id, gateway_payment_id, "mock-signature"
        )

        self.assertEqual(result["status"], "SUCCESS")

        stored = self.payment_repository.get_by_id(payment_id)
        self.assertEqual(stored.status, "SUCCESS")

        self.assertNotIn(
            payment_id,
            self.payment_cache_repository.cache,
        )

        print("PASS: Payment verified.")
        print("PASS: Status changed to SUCCESS.")
        print("PASS: Cache invalidated.")

    # =====================================================
    # TEST 4: FAILED PAYMENT AND RETRY
    # =====================================================

    def test_failed_payment_and_retry(self):

        print("\n[TEST] Failed payment and retry")

        booking_id = self.create_booking()

        first = self.service.initiate_payment(
            booking_id, f"failed-{uuid4()}", self.customer
        )

        failed_gateway_payment_id = (
            self.payment_provider.simulate_failed_payment(
                first["gateway_order_id"]
            )
        )

        failed_result = self.service.verify_payment(
            first["payment_id"],
            failed_gateway_payment_id,
            "mock-signature",
        )

        self.assertEqual(failed_result["status"], "FAILED")

        first_stored = self.payment_repository.get_by_id(
            first["payment_id"]
        )

        self.assertEqual(first_stored.status, "FAILED")

        second = self.service.initiate_payment(
            booking_id, f"retry-{uuid4()}", self.customer
        )

        self.assertNotEqual(first["payment_id"], second["payment_id"])

        successful_gateway_payment_id = (
            self.payment_provider.simulate_successful_payment(
                second["gateway_order_id"]
            )
        )

        result = self.service.verify_payment(
            second["payment_id"],
            successful_gateway_payment_id,
            "mock-signature",
        )

        self.assertEqual(result["status"], "SUCCESS")

        self.assertEqual(
            self.payment_repository.get_by_id(
                first["payment_id"]
            ).status,
            "FAILED",
        )

        self.assertEqual(
            self.payment_repository.get_by_id(
                second["payment_id"]
            ).status,
            "SUCCESS",
        )

        print("PASS: First attempt remains FAILED.")
        print("PASS: Retry created a new attempt.")
        print("PASS: Second attempt succeeded.")

    # =====================================================
    # TEST 5: DUPLICATE PAYMENT VERIFICATION
    # =====================================================

    def test_duplicate_payment_verification(self):

        print("\n[TEST] Duplicate payment verification")

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id, f"duplicate-{uuid4()}", self.customer
        )

        gateway_payment_id = (
            self.payment_provider.simulate_successful_payment(
                response["gateway_order_id"]
            )
        )

        first = self.service.verify_payment(
            response["payment_id"],
            gateway_payment_id,
            "mock-signature",
        )

        second = self.service.verify_payment(
            response["payment_id"],
            gateway_payment_id,
            "mock-signature",
        )

        self.assertEqual(first["status"], "SUCCESS")
        self.assertEqual(second["status"], "SUCCESS")

        print("PASS: Duplicate verification handled safely.")

    # =====================================================
    # TEST 6: INVALID PAYMENT SIGNATURE
    # =====================================================

    def test_invalid_payment_signature(self):

        print("\n[TEST] Invalid payment signature")

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id, f"signature-{uuid4()}", self.customer
        )

        gateway_payment_id = (
            self.payment_provider.simulate_successful_payment(
                response["gateway_order_id"]
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "Payment verification failed",
        ):
            self.service.verify_payment(
                response["payment_id"],
                gateway_payment_id,
                "invalid-signature",
            )

        stored = self.payment_repository.get_by_id(
            response["payment_id"]
        )

        self.assertEqual(stored.status, "PENDING")

        print("PASS: Invalid signature rejected.")
        print("PASS: Payment remains PENDING.")

    # =====================================================
    # TEST 7: PAYMENT AMOUNT MISMATCH
    # =====================================================

    def test_payment_amount_mismatch(self):

        print("\n[TEST] Payment amount mismatch")

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id, f"amount-{uuid4()}", self.customer
        )

        gateway_payment_id = (
            self.payment_provider.simulate_successful_payment(
                response["gateway_order_id"]
            )
        )

        self.payment_provider.payments[
            gateway_payment_id
        ]["amount"] += 100

        with self.assertRaisesRegex(
            ValueError,
            "Payment amount mismatch",
        ):
            self.service.verify_payment(
                response["payment_id"],
                gateway_payment_id,
                "mock-signature",
            )

        stored = self.payment_repository.get_by_id(
            response["payment_id"]
        )

        self.assertEqual(stored.status, "PENDING")

        print("PASS: Gateway amount mismatch rejected.")

    # =====================================================
    # TEST 8: FULL REFUND
    # =====================================================

    def test_full_refund(self):

        print("\n[TEST] Full refund")

        payment_id = self.create_successful_payment()

        result = self.service.refund_payment(
            payment_id,
            Decimal("735.00"),
            f"full-refund-{uuid4()}",
        )

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(
            Decimal(result["amount"]),
            Decimal("735.00"),
        )

        print("PASS: Full refund processed.")

    # =====================================================
    # TEST 9: PARTIAL REFUND
    # =====================================================

    def test_partial_refund(self):

        print("\n[TEST] Partial refund")

        payment_id = self.create_successful_payment()

        result = self.service.refund_payment(
            payment_id,
            Decimal("300.00"),
            f"partial-refund-{uuid4()}",
        )

        self.assertEqual(result["status"], "SUCCESS")

        remaining = self.refund_repository.get_total_refunded_amount(
            payment_id
        )

        self.assertEqual(remaining, Decimal("300.00"))

        print("PASS: Partial refund processed.")

    # =====================================================
    # TEST 10: DUPLICATE REFUND
    # =====================================================

    def test_duplicate_refund_request(self):

        print("\n[TEST] Duplicate refund request")

        payment_id = self.create_successful_payment()
        key = f"duplicate-refund-{uuid4()}"

        first = self.service.refund_payment(
            payment_id, Decimal("300.00"), key
        )

        second = self.service.refund_payment(
            payment_id, Decimal("300.00"), key
        )

        self.assertEqual(first["refund_id"], second["refund_id"])
        self.assertTrue(second["existing_attempt"])

        self.assertEqual(
            len(self.refund_repository.get_by_payment_id(payment_id)),
            1,
        )

        print("PASS: Duplicate request returned existing refund.")

    # =====================================================
    # TEST 11: REFUND EXCEEDING ORIGINAL AMOUNT
    # =====================================================

    def test_refund_exceeding_original_amount(self):

        print("\n[TEST] Refund exceeding original amount")

        payment_id = self.create_successful_payment()

        with self.assertRaisesRegex(
            ValueError,
            "Refund amount exceeds original payment amount",
        ):
            self.service.refund_payment(
                payment_id,
                Decimal("800.00"),
                f"excess-{uuid4()}",
            )

        self.assertEqual(
            len(self.refund_repository.get_by_payment_id(payment_id)),
            0,
        )

        print("PASS: Excess refund rejected.")

    # =====================================================
    # TEST 12: REFUND EXCEEDING REMAINING AMOUNT
    # =====================================================

    def test_refund_exceeding_remaining_amount(self):

        print("\n[TEST] Refund exceeding remaining amount")

        payment_id = self.create_successful_payment()

        self.service.refund_payment(
            payment_id,
            Decimal("500.00"),
            f"first-refund-{uuid4()}",
        )

        with self.assertRaisesRegex(
            ValueError,
            "Refund exceeds remaining refundable amount",
        ):
            self.service.refund_payment(
                payment_id,
                Decimal("300.00"),
                f"second-refund-{uuid4()}",
            )

        print("PASS: Remaining amount validation works.")

    # =====================================================
    # TEST 13: REFUND FOR PENDING PAYMENT
    # =====================================================

    def test_refund_for_pending_payment(self):

        print("\n[TEST] Refund for pending payment")

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id,
            f"pending-refund-{uuid4()}",
            self.customer,
        )

        with self.assertRaisesRegex(
            ValueError,
            "Only successful payments can be refunded",
        ):
            self.service.refund_payment(
                response["payment_id"],
                Decimal("100.00"),
                f"pending-refund-key-{uuid4()}",
            )

        print("PASS: Pending payment refund rejected.")

    # =====================================================
    # TEST 14: REFUND FOR FAILED PAYMENT
    # =====================================================

    def test_refund_for_failed_payment(self):

        print("\n[TEST] Refund for failed payment")

        booking_id = self.create_booking()

        response = self.service.initiate_payment(
            booking_id,
            f"failed-refund-{uuid4()}",
            self.customer,
        )

        failed_gateway_payment_id = (
            self.payment_provider.simulate_failed_payment(
                response["gateway_order_id"]
            )
        )

        self.service.verify_payment(
            response["payment_id"],
            failed_gateway_payment_id,
            "mock-signature",
        )

        with self.assertRaisesRegex(
            ValueError,
            "Only successful payments can be refunded",
        ):
            self.service.refund_payment(
                response["payment_id"],
                Decimal("100.00"),
                f"failed-refund-key-{uuid4()}",
            )

        print("PASS: Failed payment refund rejected.")

    # =====================================================
    # TEST 15: GATEWAY REFUND FAILURE
    # =====================================================

    def test_gateway_refund_failure(self):

        print("\n[TEST] Gateway refund failure")

        payment_id = self.create_successful_payment()

        self.payment_provider.simulate_refund_failure()

        result = self.service.refund_payment(
            payment_id,
            Decimal("200.00"),
            f"gateway-failure-{uuid4()}",
        )

        self.assertEqual(result["status"], "FAILED")

        self.assertEqual(
            self.refund_repository.get_total_refunded_amount(payment_id),
            Decimal("0.00"),
        )

        print("PASS: Gateway rejection recorded as FAILED.")
        print("PASS: Failed refund does not reserve refundable amount.")

    # =====================================================
    # TEST 16: GATEWAY REFUND TIMEOUT
    # =====================================================

    def test_gateway_refund_timeout(self):

        print("\n[TEST] Gateway refund timeout")

        payment_id = self.create_successful_payment()

        self.payment_provider.simulate_refund_timeout()

        result = self.service.refund_payment(
            payment_id,
            Decimal("200.00"),
            f"gateway-timeout-{uuid4()}",
        )

        self.assertEqual(result["status"], "UNKNOWN")

        self.assertEqual(
            self.refund_repository.get_total_refunded_amount(payment_id),
            Decimal("200.00"),
        )

        print("PASS: Timeout recorded as UNKNOWN.")
        print("PASS: Uncertain refund amount remains reserved.")

    # =====================================================
    # TEST 17: INCOMPLETE GATEWAY RESPONSE
    # =====================================================

    def test_incomplete_refund_response(self):

        print("\n[TEST] Incomplete refund response")

        payment_id = self.create_successful_payment()

        self.payment_provider.simulate_incomplete_refund_response()

        result = self.service.refund_payment(
            payment_id,
            Decimal("150.00"),
            f"incomplete-refund-{uuid4()}",
        )

        self.assertEqual(result["status"], "UNKNOWN")

        self.assertEqual(
            self.refund_repository.get_total_refunded_amount(payment_id),
            Decimal("150.00"),
        )

        print("PASS: Incomplete response recorded as UNKNOWN.")
        print("PASS: Refund amount remains reserved.")

    # =====================================================
    # TEST 18: MULTIPLE PARTIAL REFUNDS
    # =====================================================

    def test_multiple_partial_refunds(self):

        print("\n[TEST] Multiple partial refunds")

        payment_id = self.create_successful_payment()

        amounts = [
            Decimal("300.00"),
            Decimal("200.00"),
            Decimal("235.00"),
        ]

        for amount in amounts:

            result = self.service.refund_payment(
                payment_id,
                amount,
                f"partial-{uuid4()}",
            )

            self.assertEqual(result["status"], "SUCCESS")

        total = self.refund_repository.get_total_refunded_amount(
            payment_id
        )

        self.assertEqual(total, Decimal("735.00"))

        with self.assertRaisesRegex(
            ValueError,
            "Refund exceeds remaining refundable amount",
        ):
            self.service.refund_payment(
                payment_id,
                Decimal("1.00"),
                f"extra-{uuid4()}",
            )

        print("PASS: Three partial refunds processed.")
        print("PASS: Total refunded equals ₹735.")
        print("PASS: Additional refund rejected.")


    # =====================================================
    # TEST 19: RECONCILE REFUND AFTER GATEWAY TIMEOUT
    # =====================================================

    def test_reconcile_refund_after_timeout(self):

        print("\n[TEST] Reconcile refund after timeout")

        payment_id = self.create_successful_payment()

        self.payment_provider.simulate_refund_timeout()

        refund_result = self.service.refund_payment(
            payment_id,
            Decimal("200.00"),
            f"reconcile-timeout-{uuid4()}",
        )

        self.assertEqual(refund_result["status"], "UNKNOWN")

        refund_id = refund_result["refund_id"]

        reconciled = self.service.reconcile_refund(refund_id)

        self.assertEqual(reconciled["status"], "SUCCESS")
        self.assertIsNotNone(reconciled["gateway_refund_id"])

        stored_refund = self.refund_repository.get_by_id(refund_id)
        self.assertEqual(stored_refund.status, "SUCCESS")

        print("PASS: Timeout initially recorded as UNKNOWN.")
        print("PASS: Gateway status lookup reconciled it to SUCCESS.")

    # =====================================================
    # TEST 20: RECONCILE REFUND AFTER INCOMPLETE RESPONSE
    # =====================================================

    def test_reconcile_refund_after_incomplete_response(self):

        print("\n[TEST] Reconcile refund after incomplete response")

        payment_id = self.create_successful_payment()

        self.payment_provider.simulate_incomplete_refund_response()

        refund_result = self.service.refund_payment(
            payment_id,
            Decimal("150.00"),
            f"reconcile-incomplete-{uuid4()}",
        )

        self.assertEqual(refund_result["status"], "UNKNOWN")

        refund_id = refund_result["refund_id"]

        reconciled = self.service.reconcile_refund(refund_id)

        self.assertEqual(reconciled["status"], "SUCCESS")
        self.assertIsNotNone(reconciled["gateway_refund_id"])

        stored_refund = self.refund_repository.get_by_id(refund_id)
        self.assertEqual(stored_refund.status, "SUCCESS")

        print("PASS: Incomplete response initially recorded as UNKNOWN.")
        print("PASS: Gateway status lookup reconciled it to SUCCESS.")

    # =====================================================
    # TEST 21: RECONCILE ALREADY COMPLETED REFUND
    # =====================================================

    def test_reconcile_already_completed_refund(self):

        print("\n[TEST] Reconcile already completed refund")

        payment_id = self.create_successful_payment()

        refund_result = self.service.refund_payment(
            payment_id,
            Decimal("100.00"),
            f"reconcile-completed-{uuid4()}",
        )

        self.assertEqual(refund_result["status"], "SUCCESS")

        # A terminal refund should be returned without another gateway lookup.
        reconciled = self.service.reconcile_refund(
            refund_result["refund_id"]
        )

        self.assertEqual(reconciled["status"], "SUCCESS")
        self.assertEqual(
            reconciled["gateway_refund_id"],
            refund_result["gateway_refund_id"],
        )

        print("PASS: Completed refund remains SUCCESS.")
        print("PASS: Existing gateway refund ID is preserved.")


# =========================================================
# TEST RUNNER
# =========================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
