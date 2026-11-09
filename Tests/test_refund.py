
from datetime import date
from decimal import Decimal
from uuid import uuid4

from core.database import SessionLocal

from models.Booking import Booking

from Repositories.BookingRepository import BookingRepository
from Repositories.PaymentRepository import PaymentRepository
from Repositories.PaymentCacheRepository import PaymentCacheRepository
from Repositories.RefundRepository import RefundRepository

from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor

from Adaptors.Payments.MockPaymentAdapter import MockPaymentAdapter

from Services.Payments.PaymentService import PaymentService


def test_payment_refund():

    database = SessionLocal()

    redis_adaptee = RedisCacheAdaptee()
    redis_cache = RedisCacheAdaptor(redis_adaptee)

    payment_id = None

    try:
        # 1. Initialize repositories and gateway.
        booking_repository = BookingRepository(database)
        payment_repository = PaymentRepository(database)
        refund_repository = RefundRepository(database)

        payment_cache_repository = PaymentCacheRepository(redis_cache)

        mock_gateway = MockPaymentAdapter()

        payment_service = PaymentService(
            payment_provider=mock_gateway,
            payment_repository=payment_repository,
            booking_repository=booking_repository,
            payment_cache_repository=payment_cache_repository,
            refund_repository=refund_repository,
            gateway_name="MOCK",
        )

        # 2. Create a fresh booking.
        booking = Booking(
            user_id="TEST_USER_001",
            operator_booking_ref=f"REFUND-TEST-{uuid4()}",
            source_city_id="3",
            destination_city_id="5",
            journey_date=date(2026, 11, 15),
            bus_id="TEST_BUS_001",
            seat_numbers=["A1"],
            total_amount=Decimal("1000.00"),
            currency="INR",
            status="PENDING",
        )

        booking_repository.save(booking)
        database.commit()

        print("Booking created:", booking.id)

        # 3. Initiate payment.
        payment_response = payment_service.initiate_payment(
            booking_id=booking.id,
            idempotency_key=f"refund-payment-{uuid4()}",
            customer={
                "name": "Test User",
                "email": "test@example.com",
                "contact": "9999999999",
            },
        )

        payment_id = payment_response["payment_id"]
        gateway_order_id = payment_response["gateway_order_id"]

        print("Payment initiated:", payment_id)

        # 4. Simulate successful payment.
        gateway_payment_id = (
            mock_gateway.simulate_successful_payment(
                gateway_order_id
            )
        )

        # 5. Verify payment.
        verification_response = payment_service.verify_payment(
            payment_id=payment_id,
            gateway_payment_id=gateway_payment_id,
            signature="mock-test-signature",
        )

        assert verification_response["status"] == "SUCCESS"

        print("Payment verified:", verification_response["status"])

        # ------------------------------------------------
        # TEST 1: Partial refund of Rs. 100
        # ------------------------------------------------

        print("\nTEST 1: Partial refund of Rs. 100")

        first_refund_key = f"refund-100-{uuid4()}"

        first_refund = payment_service.refund_payment(
            payment_id=payment_id,
            amount=Decimal("100.00"),
            idempotency_key=first_refund_key,
        )

        print("Refund response:", first_refund)

        assert first_refund["status"] == "SUCCESS"
        assert Decimal(first_refund["amount"]) == Decimal("100.00")

        # Verify PostgreSQL record.
        database.expire_all()

        first_refund_record = (
            refund_repository.get_by_id(
                first_refund["refund_id"]
            )
        )

        assert first_refund_record is not None
        assert first_refund_record.status == "SUCCESS"

        print("Partial refund saved in PostgreSQL")

        # ------------------------------------------------
        # TEST 2: Duplicate refund request
        # ------------------------------------------------

        print("\nTEST 2: Duplicate refund request")

        duplicate_refund = payment_service.refund_payment(
            payment_id=payment_id,
            amount=Decimal("100.00"),
            idempotency_key=first_refund_key,
        )

        assert duplicate_refund["refund_id"] == first_refund["refund_id"]
        assert duplicate_refund["existing_attempt"] is True

        print("Duplicate request prevented successfully")

        # ------------------------------------------------
        # TEST 3: Another partial refund of Rs. 200
        # ------------------------------------------------

        print("\nTEST 3: Another partial refund of Rs. 200")

        second_refund = payment_service.refund_payment(
            payment_id=payment_id,
            amount=Decimal("200.00"),
            idempotency_key=f"refund-200-{uuid4()}",
        )

        assert second_refund["status"] == "SUCCESS"

        print("Second partial refund successful")

        # ------------------------------------------------
        # TEST 4: Check total refunded amount
        # ------------------------------------------------

        print("\nTEST 4: Check total refunded amount")

        total_refunded = (
            refund_repository.get_total_refunded_amount(
                payment_id
            )
        )

        assert Decimal(str(total_refunded)) == Decimal("300.00")

        remaining = Decimal("1000.00") - Decimal(
            str(total_refunded)
        )

        print("Total refunded:", total_refunded)
        print("Remaining refundable amount:", remaining)

        # ------------------------------------------------
        # TEST 5: Reject refund exceeding remaining amount
        # ------------------------------------------------

        print("\nTEST 5: Reject excessive refund")

        try:
            payment_service.refund_payment(
                payment_id=payment_id,
                amount=Decimal("800.01"),
                idempotency_key=f"refund-excess-{uuid4()}",
            )

            raise AssertionError(
                "Expected excessive refund to be rejected"
            )

        except ValueError as error:
            assert "Refund exceeds remaining" in str(error)
            print("Excessive refund correctly rejected:", error)

        # ------------------------------------------------
        # TEST 6: Refund remaining Rs. 700
        # ------------------------------------------------

        print("\nTEST 6: Refund remaining Rs. 700")

        final_refund = payment_service.refund_payment(
            payment_id=payment_id,
            amount=Decimal("700.00"),
            idempotency_key=f"refund-final-{uuid4()}",
        )

        assert final_refund["status"] == "SUCCESS"

        print("Remaining refund successful")

        # ------------------------------------------------
        # TEST 7: Ensure no more refunds are possible
        # ------------------------------------------------

        print("\nTEST 7: Reject refund after full refund")

        try:
            payment_service.refund_payment(
                payment_id=payment_id,
                amount=Decimal("1.00"),
                idempotency_key=f"refund-after-full-{uuid4()}",
            )

            raise AssertionError(
                "Expected refund to be rejected"
            )

        except ValueError as error:
            assert "Refund exceeds remaining" in str(error)
            print("Additional refund correctly rejected")

        # ------------------------------------------------
        # TEST 8: Original payment remains SUCCESS
        # ------------------------------------------------

        print("\nTEST 8: Verify original payment status")

        database.expire_all()

        original_payment = payment_repository.get_by_id(payment_id)

        assert original_payment.status == "SUCCESS"

        print("Original payment status:", original_payment.status)

        # ------------------------------------------------
        # FINAL RESULT
        # ------------------------------------------------

        print("\nALL REFUND TESTS PASSED")

    finally:
        if payment_id:
            payment_cache_repository.invalidate_payment_status(
                payment_id
            )

        database.close()
        redis_adaptee.close()


if __name__ == "__main__":
    test_payment_refund()
