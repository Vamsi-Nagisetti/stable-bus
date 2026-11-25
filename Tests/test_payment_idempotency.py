
from dotenv import load_dotenv
from sqlalchemy import select
import uuid
from core.database import SessionLocal
from models.Booking import Booking
from models.Payment import Payment
from uuid import uuid4
from Repositories.BookingRepository import BookingRepository
from Repositories.PaymentRepository import PaymentRepository

from Services.Payments.PaymentService import PaymentService
from Adaptors.Payments.MockPaymentAdapter import MockPaymentAdapter


load_dotenv()


def test_payment_idempotency():

    database = SessionLocal()

    try:
        # 1. Create a test booking
        booking = Booking(
            user_id="TEST_USER_001",
            operator_booking_ref="TEST_BOOKING_001",
            source_city_id="3",
            destination_city_id="5",
            journey_date="2026-11-15",
            bus_id="TEST_BUS_001",
            seat_numbers=["A1"],
            total_amount=500,
            currency="INR",
            status="PENDING",
        )

        booking_repository = BookingRepository(database)
        payment_repository = PaymentRepository(database)

        booking_repository.save(booking)
        database.commit()
        database.refresh(booking)

        print("Test booking created:", booking.id)

        # 2. Initialize mock gateway and service
        mock_gateway = MockPaymentAdapter()

        payment_service = PaymentService(
            payment_provider=mock_gateway,
            payment_repository=payment_repository,
            booking_repository=booking_repository,
            gateway_name="MOCK",
        )

        idempotency_key = f"stablebus-idempotency-test-{uuid4()}"

        # 3. First payment request
        print("\nFirst payment request...")

        first_response = payment_service.initiate_payment(
            booking_id=booking.id,
            idempotency_key=idempotency_key,
            customer={
                "customer_id": "TEST_USER_001",
                "email": "test@example.com",
                "phone": "9999999999",
            },
        )

        print(first_response)

        # 4. Second request with the same key
        print("\nSecond payment request with same key...")

        second_response = payment_service.initiate_payment(
            booking_id=booking.id,
            idempotency_key=idempotency_key,
            customer={
                "customer_id": "TEST_USER_001",
            },
        )

        print(second_response)

        # 5. Verify results
        assert first_response["payment_id"] == second_response["payment_id"]

        assert first_response["status"] == "PENDING"
        assert second_response["status"] == "PENDING"

        assert second_response["existing_attempt"] is True

        # Only one payment record should exist for this key.
        payment = payment_repository.get_by_idempotency_key(
            idempotency_key
        )

        assert payment is not None

        print("\nPayment record:", payment.id)
        print("Gateway order:", payment.gateway_order_id)
        print("Payment status:", payment.status)

        print("\nIDEMPOTENCY TEST PASSED!")

        # Create another booking
        another_booking = Booking(
            user_id="TEST_USER_002",
            operator_booking_ref="TEST_BOOKING_002",
            source_city_id="3",
            destination_city_id="5",
            journey_date="2026-11-15",
            bus_id="TEST_BUS_002",
            seat_numbers=["A2"],
            total_amount=600,
            currency="INR",
            status="PENDING",
        )

        booking_repository.save(another_booking)
        database.commit()

        print("\nTesting same idempotency key with another booking...")

        try:
            payment_service.initiate_payment(
                booking_id=another_booking.id,
                idempotency_key=idempotency_key,
                customer={"customer_id": "TEST_USER_002"},
            )

            raise AssertionError("Expected ValueError was not raised")

        except ValueError as error:
            assert str(error) == (
                "Idempotency key already belongs to another booking"
            )
            print("Correctly rejected:", error)
        print("\nTesting same booking with a new idempotency key...")

        third_response = payment_service.initiate_payment(
            booking_id=booking.id,
            idempotency_key=f"stablebus-retry-{uuid4()}",
            customer={
                "customer_id": "TEST_USER_001",
            },
        )

        print(third_response)

        assert third_response["payment_id"] != first_response["payment_id"]
        assert third_response["payment_attempt_id"] != first_response["payment_attempt_id"]
        assert third_response["gateway_order_id"] != first_response["gateway_order_id"]

        print("\nNEW PAYMENT ATTEMPT TEST PASSED!")

    finally:
        database.rollback()
        database.close()


if __name__ == "__main__":
    test_payment_idempotency()
