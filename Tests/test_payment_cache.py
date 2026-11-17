
from core.database import SessionLocal

from Repositories.PaymentRepository import PaymentRepository
from Repositories.BookingRepository import BookingRepository
from Repositories.PaymentCacheRepository import PaymentCacheRepository

from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor

from Adaptors.Payments.MockPaymentAdapter import MockPaymentAdapter
from Services.Payments.PaymentService import PaymentService


def test_payment_status_cache():

    database = SessionLocal()
    redis_adaptee = RedisCacheAdaptee()

    try:
        payment_repository = PaymentRepository(database)
        booking_repository = BookingRepository(database)

        redis_adaptor = RedisCacheAdaptor(redis_adaptee)
        payment_cache_repository = PaymentCacheRepository(redis_adaptor)

        payment_service = PaymentService(
            payment_provider=MockPaymentAdapter(),
            payment_repository=payment_repository,
            booking_repository=booking_repository,
            payment_cache_repository=payment_cache_repository,
            gateway_name="MOCK",
        )

        # Use an existing payment from your previous idempotency test.
        payment = database.query(
            __import__("models.Payment", fromlist=["Payment"]).Payment
        ).filter_by(
            gateway="MOCK",
            status="PENDING"
        ).first()

        assert payment is not None, "No MOCK PENDING payment found"

        payment_id = payment.id

        print("Testing payment:", payment_id)

        # Clear cache before testing.
        payment_cache_repository.invalidate_payment_status(payment_id)

        # First request: PostgreSQL read and Redis population.
        first_result = payment_service.get_payment_status(payment_id)

        print("\nFirst request:", first_result)

        assert first_result["cache_hit"] is False

        # Second request: Redis hit.
        second_result = payment_service.get_payment_status(payment_id)

        print("\nSecond request:", second_result)

        assert second_result["cache_hit"] is True
        assert second_result["status"] == first_result["status"]

        print("\nPAYMENT STATUS CACHE TEST PASSED!")

    finally:
        database.close()
        redis_adaptee.close()


if __name__ == "__main__":
    test_payment_status_cache()
