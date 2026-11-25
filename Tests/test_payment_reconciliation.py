
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


def test_reconcile_captured_payment_without_callback():
    database = SessionLocal()
    redis_adaptee = RedisCacheAdaptee()
    redis_cache = RedisCacheAdaptor(redis_adaptee)

    payment_id = None

    try:
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

        booking = Booking(
            user_id="TEST_USER_001",
            operator_booking_ref=f"RECON-{uuid4()}",
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

        initiated = payment_service.initiate_payment(
            booking_id=booking.id,
            idempotency_key=f"reconcile-{uuid4()}",
            customer={
                "name": "Test User",
                "email": "test@example.com",
                "contact": "9999999999",
            },
        )

        payment_id = initiated["payment_id"]
        gateway_order_id = initiated["gateway_order_id"]

        # Razorpay captures the payment, but the callback is never sent.
        gateway_payment_id = mock_gateway.simulate_successful_payment(
            gateway_order_id
        )

        result = payment_service.reconcile_payment(payment_id)

        database.expire_all()
        payment = payment_repository.get_by_id(payment_id)

        assert result["status"] == "SUCCESS"
        assert payment.status == "SUCCESS"
        assert payment.gateway_payment_id == gateway_payment_id

        # Reconciliation must be idempotent.
        second_result = payment_service.reconcile_payment(payment_id)
        assert second_result["status"] == "SUCCESS"

    finally:
        if payment_id:
            payment_cache_repository.invalidate_payment_status(payment_id)

        database.close()
        redis_adaptee.close()
