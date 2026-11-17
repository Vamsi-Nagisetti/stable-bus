
from datetime import date
from uuid import uuid4

from core.database import SessionLocal

from models.Booking import Booking
from Repositories.BookingRepository import BookingRepository
from Repositories.PaymentRepository import PaymentRepository
from Repositories.PaymentCacheRepository import PaymentCacheRepository

from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor

from Adaptors.Payments.MockPaymentAdapter import MockPaymentAdapter
from Services.Payments.PaymentService import PaymentService


def test_payment_verification():

    database = SessionLocal()

    redis_adaptee = RedisCacheAdaptee()
    redis_cache = RedisCacheAdaptor(redis_adaptee)
    payment_cache_repository = PaymentCacheRepository(redis_cache)

    payment_id = None

    try:
        # 1. Initialize repositories and the mock gateway.
        booking_repository = BookingRepository(database)
        payment_repository = PaymentRepository(database)

        mock_gateway = MockPaymentAdapter()

        payment_service = PaymentService(
            payment_provider=mock_gateway,
            payment_repository=payment_repository,
            booking_repository=booking_repository,
            payment_cache_repository=payment_cache_repository,
            gateway_name="MOCK",
        )

        # 2. Create a fresh booking.
        booking = Booking(
            user_id="TEST_USER_001",
            operator_booking_ref=f"VERIFY-{uuid4()}",
            source_city_id="3",
            destination_city_id="5",
            journey_date=date(2026, 11, 15),
            bus_id="TEST_BUS_001",
            seat_numbers=["A1"],
            total_amount=500,
            currency="INR",
            status="PENDING",
        )

        booking_repository.save(booking)
        database.commit()

        print("Booking created:", booking.id)

        # 3. Initiate payment using this mock gateway instance.
        idempotency_key = f"verify-test-{uuid4()}"

        response = payment_service.initiate_payment(
            booking_id=booking.id,
            idempotency_key=idempotency_key,
            customer={
                "name": "Test User",
                "email": "test@example.com",
                "contact": "9999999999",
            },
        )

        payment_id = response["payment_id"]
        gateway_order_id = response["gateway_order_id"]

        print("Payment initiated:", payment_id)
        print("Gateway order:", gateway_order_id)

        # 4. Verify initial status and Redis caching.
        first_status = payment_service.get_payment_status(payment_id)

        assert first_status["status"] == "PENDING"
        assert first_status["cache_hit"] is False

        second_status = payment_service.get_payment_status(payment_id)

        assert second_status["cache_hit"] is True

        print("Initial payment status:", first_status["status"])
        print("Redis cache hit:", second_status["cache_hit"])

        # 5. Simulate successful payment using THE SAME gateway instance.
        gateway_payment_id = mock_gateway.simulate_successful_payment(
            gateway_order_id
        )

        print("Mock gateway payment:", gateway_payment_id)

        # 6. Verify payment.
        verification_response = payment_service.verify_payment(
            payment_id=payment_id,
            gateway_payment_id=gateway_payment_id,
            signature="mock-test-signature",
        )

        print("Verification response:", verification_response)

        assert verification_response["status"] == "SUCCESS"

        # 7. Verify PostgreSQL has SUCCESS status.
        payment = payment_repository.get_by_id(payment_id)
        database.refresh(payment)

        assert payment.status == "SUCCESS"
        assert payment.gateway_payment_id == gateway_payment_id

        print("PostgreSQL status:", payment.status)

        # 8. Verify payment cache was invalidated.
        cached_status = payment_cache_repository.get_payment_status(payment_id)

        assert cached_status is None

        print("Redis cache invalidated successfully")

        # 9. Read status again; it should come from PostgreSQL.
        updated_status = payment_service.get_payment_status(payment_id)

        assert updated_status["status"] == "SUCCESS"
        assert updated_status["cache_hit"] is False

        print("Updated status:", updated_status["status"])
        print("Cache hit after invalidation:", updated_status["cache_hit"])

        print("\nPAYMENT VERIFICATION TEST PASSED")

    finally:
        if payment_id:
            payment_cache_repository.invalidate_payment_status(payment_id)

        database.close()
        redis_adaptee.close()


if __name__ == "__main__":
    test_payment_verification()
