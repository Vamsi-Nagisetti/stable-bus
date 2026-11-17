
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from Orchestrators.booking_orchestrator import (
    BookingOrchestrator,
    BookingOrchestrationError,
)
from core.constants.booking_status import BookingStatus


def build_test_data():
    passenger = {
        "name": "Test Passenger",
        "age": 25,
        "gender": "male",
        "seat_key": "SEAT001",
        "title": "Mr",
        "dob": None,
    }

    request = SimpleNamespace(
        source_city_id="HYD",
        destination_city_id="BLR",
        journey_date=date(2026, 12, 1),
        bus_id="BUS001",
        search_key="SEARCH001",
        boarding_id="BOARD001",
        dropping_id="DROP001",
        passengers=[passenger],
    )

    seat_map_response = {
        "response_Header": {"error_Code": "0000"},
        "seatMap_Key": "MAP001",
        "seatMap": [
            {
                "seat_Key": "SEAT001",
                "seat_Number": "U1",
                "bookable": True,
                "ladies_Seat": False,
                "fareMaster": {"total_Amount": "838.96"},
            }
        ],
    }

    return request, seat_map_response


def mock_booking(status=BookingStatus.TEMP_BOOKED):
    return SimpleNamespace(
        id="booking-001",
        user_id="user-001",
        status=status,
        supplier_refno=None,
        transport_pnr=None,
        passengers=[],
    )


def setup_booking_repository(monkeypatch, booking):
    repository = MagicMock()
    repository.get_by_id.return_value = booking

    monkeypatch.setattr(
        "Orchestrators.booking_orchestrator.BookingRepository",
        lambda db: repository,
    )
    return repository


# =========================================================
# TEMPORARY BOOKING TESTS
# =========================================================

def test_start_booking_success():
    request, seat_map_response = build_test_data()

    db = MagicMock()
    passenger_repository = MagicMock()
    passenger_repository.get_passengers.return_value = []

    adapter = MagicMock()
    adapter.BusTempBooking.return_value = {
        "response_Header": {"error_Code": "0000"},
        "booking_RefNo": "MOCK12345",
    }

    booking = BookingOrchestrator.start_booking(
        db=db,
        user_id="1",
        request=request,
        passenger_repository=passenger_repository,
        adapter=adapter,
        seat_map_response=seat_map_response,
        customer_mobile="9999999999",
        passenger_email="test@example.com",
    )

    assert booking.status == BookingStatus.TEMP_BOOKED
    assert booking.temp_booking_ref == "MOCK12345"
    assert booking.total_amount == Decimal("838.96")

    adapter.BusTempBooking.assert_called_once()
    db.commit.assert_called_once()


def test_start_booking_provider_rejection():
    request, seat_map_response = build_test_data()

    db = MagicMock()
    passenger_repository = MagicMock()
    passenger_repository.get_passengers.return_value = []

    adapter = MagicMock()
    adapter.BusTempBooking.return_value = {
        "response_Header": {
            "error_Code": "5001",
            "error_Desc": "Seat booking failed",
        }
    }

    with pytest.raises(BookingOrchestrationError):
        BookingOrchestrator.start_booking(
            db=db,
            user_id="1",
            request=request,
            passenger_repository=passenger_repository,
            adapter=adapter,
            seat_map_response=seat_map_response,
            customer_mobile="9999999999",
            passenger_email="test@example.com",
        )

    db.commit.assert_called_once()


def test_start_booking_provider_timeout():
    request, seat_map_response = build_test_data()

    db = MagicMock()
    passenger_repository = MagicMock()
    passenger_repository.get_passengers.return_value = []

    adapter = MagicMock()
    adapter.BusTempBooking.side_effect = TimeoutError("Provider timeout")

    with pytest.raises(BookingOrchestrationError):
        BookingOrchestrator.start_booking(
            db=db,
            user_id="1",
            request=request,
            passenger_repository=passenger_repository,
            adapter=adapter,
            seat_map_response=seat_map_response,
            customer_mobile="9999999999",
            passenger_email="test@example.com",
        )

    db.commit.assert_called_once()


# =========================================================
# PAYMENT INITIATION TESTS
# =========================================================

def test_initiate_booking_payment_success(monkeypatch):
    booking = mock_booking()
    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    payment_service = MagicMock()
    payment_service.initiate_payment.return_value = {
        "payment_id": "payment-001",
        "payment_attempt_id": "attempt-001",
        "gateway_order_id": "order-001",
        "amount": "838.96",
        "currency": "INR",
        "status": "PENDING",
        "existing_attempt": False,
    }

    result = BookingOrchestrator.initiate_booking_payment(
        db=db,
        booking_id="booking-001",
        user_id="user-001",
        payment_service=payment_service,
        customer={"name": "Test User", "email": "test@example.com"},
        idempotency_key="booking-payment:booking-001",
    )

    assert booking.status == BookingStatus.PAYMENT_PENDING
    assert result["booking_id"] == "booking-001"
    assert result["payment_id"] == "payment-001"
    assert result["status"] == "PENDING"

    payment_service.initiate_payment.assert_called_once_with(
        booking_id="booking-001",
        idempotency_key="booking-payment:booking-001",
        customer={"name": "Test User", "email": "test@example.com"},
    )
    db.commit.assert_called_once()


def test_initiate_booking_payment_idempotent_retry(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_PENDING)
    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    payment_service = MagicMock()
    payment_service.initiate_payment.return_value = {
        "payment_id": "payment-001",
        "status": "PENDING",
        "existing_attempt": True,
    }

    kwargs = {
        "db": db,
        "booking_id": "booking-001",
        "user_id": "user-001",
        "payment_service": payment_service,
        "customer": {"name": "Test User"},
        "idempotency_key": "booking-payment:booking-001",
    }

    first_result = BookingOrchestrator.initiate_booking_payment(**kwargs)
    second_result = BookingOrchestrator.initiate_booking_payment(**kwargs)

    assert first_result["payment_id"] == second_result["payment_id"]
    assert second_result["existing_attempt"] is True

    assert payment_service.initiate_payment.call_count == 2
    assert all(
        call.kwargs["idempotency_key"] == "booking-payment:booking-001"
        for call in payment_service.initiate_payment.call_args_list
    )

    # Booking was already PAYMENT_PENDING, so no additional transition commit.
    db.commit.assert_not_called()


# =========================================================
# PAYMENT VERIFICATION TESTS
# =========================================================

def test_verify_booking_payment_success(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_PENDING)
    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    payment_service = MagicMock()

    payment_service.payment_repository.get_by_id.return_value = (
        SimpleNamespace(
            id="payment-001",
            booking_id="booking-001",
        )
    )

    payment_service.verify_payment.return_value = {
        "payment_id": "payment-001",
        "gateway_payment_id": "gateway-payment-001",
        "status": "SUCCESS",
        "message": "Payment verified successfully",
    }

    result = BookingOrchestrator.verify_booking_payment(
        db=db,
        booking_id="booking-001",
        user_id="user-001",
        payment_service=payment_service,
        payment_id="payment-001",
        gateway_payment_id="gateway-payment-001",
        signature="test-signature",
    )

    assert result["status"] == "SUCCESS"
    assert result["booking_status"] == BookingStatus.PAYMENT_VERIFIED
    assert booking.status == BookingStatus.PAYMENT_VERIFIED

    payment_service.verify_payment.assert_called_once_with(
        payment_id="payment-001",
        gateway_payment_id="gateway-payment-001",
        signature="test-signature",
    )
    db.commit.assert_called_once()


def test_verify_booking_payment_not_captured(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_PENDING)
    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    payment_service = MagicMock()

    payment_service.payment_repository.get_by_id.return_value = (
        SimpleNamespace(
            id="payment-001",
            booking_id="booking-001",
        )
    )

    payment_service.verify_payment.return_value = {
        "payment_id": "payment-001",
        "status": "PENDING",
    }

    result = BookingOrchestrator.verify_booking_payment(
        db=db,
        booking_id="booking-001",
        user_id="user-001",
        payment_service=payment_service,
        payment_id="payment-001",
        gateway_payment_id="gateway-payment-001",
        signature="test-signature",
    )

    assert result["status"] == "PENDING"
    assert booking.status == BookingStatus.PAYMENT_PENDING
    db.commit.assert_not_called()


def test_verify_booking_payment_rejects_wrong_payment(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_PENDING)
    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    payment_service = MagicMock()

    payment_service.payment_repository.get_by_id.return_value = (
        SimpleNamespace(
            id="payment-001",
            booking_id="another-booking",
        )
    )

    with pytest.raises(
        BookingOrchestrationError,
        match="Payment does not belong to this booking",
    ):
        BookingOrchestrator.verify_booking_payment(
            db=db,
            booking_id="booking-001",
            user_id="user-001",
            payment_service=payment_service,
            payment_id="payment-001",
            gateway_payment_id="gateway-payment-001",
            signature="test-signature",
        )

    payment_service.verify_payment.assert_not_called()


# =========================================================
# TICKETING TESTS
# =========================================================

def test_complete_ticketing_success_acknowledgement(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_VERIFIED)
    booking.temp_booking_ref = "MOCK12345"
    booking.supplier_refno = None
    booking.transport_pnr = None

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()

    adapter.BusTicketing.return_value = {
        "booking_RefNo": "MOCK12345",
        "response_Header": {
            "error_Code": "0000",
            "error_Desc": "SUCCESS",
            "status_Id": "11",
        },
        "supplier_Refno": "SUP123",
        "transport_PNR": "PNR123",
        "statuss": "FALSE",
    }

    result = BookingOrchestrator.complete_ticketing(
        db=db,
        booking_id="booking-001",
        user_id="user-001",
        adapter=adapter,
    )

    assert result["booking_status"] == BookingStatus.TICKETING_UNKNOWN
    assert result["supplier_refno"] == "SUP123"
    assert result["transport_pnr"] == "PNR123"

    assert booking.supplier_refno == "SUP123"
    assert booking.transport_pnr == "PNR123"

    adapter.BusTicketing.assert_called_once_with({
        "booking_RefNo": "MOCK12345",
    })

    assert db.commit.call_count == 2


def test_complete_ticketing_timeout(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_VERIFIED)
    booking.temp_booking_ref = "MOCK12345"
    booking.supplier_refno = None
    booking.transport_pnr = None

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()
    adapter.BusTicketing.side_effect = TimeoutError("Provider timeout")

    result = BookingOrchestrator.complete_ticketing(
        db=db,
        booking_id="booking-001",
        user_id="user-001",
        adapter=adapter,
    )

    assert result["booking_status"] == BookingStatus.TICKETING_UNKNOWN
    assert db.commit.call_count == 2
    adapter.BusTicketing.assert_called_once()


def test_complete_ticketing_provider_rejection(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_VERIFIED)
    booking.temp_booking_ref = "MOCK12345"
    booking.supplier_refno = None
    booking.transport_pnr = None

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()

    adapter.BusTicketing.return_value = {
        "booking_RefNo": "MOCK12345",
        "response_Header": {
            "error_Code": "4001",
            "error_Desc": "Ticketing rejected",
        },
    }

    result = BookingOrchestrator.complete_ticketing(
        db=db,
        booking_id="booking-001",
        user_id="user-001",
        adapter=adapter,
    )

    assert result["booking_status"] == BookingStatus.BOOKING_FAILED
    assert result["provider_error_code"] == "4001"
    assert db.commit.call_count == 2


def test_complete_ticketing_prevents_duplicate_call(monkeypatch):
    booking = mock_booking(BookingStatus.TICKETING_UNKNOWN)
    booking.temp_booking_ref = "MOCK12345"

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()

    with pytest.raises(
        BookingOrchestrationError,
        match="Ticketing cannot start",
    ):
        BookingOrchestrator.complete_ticketing(
            db=db,
            booking_id="booking-001",
            user_id="user-001",
            adapter=adapter,
        )

    adapter.BusTicketing.assert_not_called()
    db.commit.assert_not_called()


# =========================================================
# TICKETING REQUERY TESTS
# =========================================================

def test_requery_mock_confirmed(monkeypatch):
    booking = mock_booking(BookingStatus.TICKETING_UNKNOWN)
    booking.temp_booking_ref = "MOCK12345"

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()
    adapter.BusRequery.return_value = {
        "booking_RefNo": "MOCK12345",
        "mock_status": "CONFIRMED",
    }

    result = BookingOrchestrator.requery_ticketing(
        db, "booking-001", "user-001", adapter
    )

    assert result["booking_status"] == BookingStatus.CONFIRMED
    adapter.BusRequery.assert_called_once_with({
        "booking_RefNo": "MOCK12345",
    })
    db.commit.assert_called_once()


def test_requery_all_passengers_confirmed(monkeypatch):
    booking = mock_booking(BookingStatus.TICKETING_UNKNOWN)
    booking.temp_booking_ref = "MOCK12345"
    booking.passengers = [
        SimpleNamespace(id="p1", seat_number="A1", ticket_number=None),
        SimpleNamespace(id="p2", seat_number="A2", ticket_number=None),
    ]

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()
    adapter.BusRequery.return_value = {
        "booking_RefNo": "MOCK12345",
        "response_Header": {"error_Code": "0000"},
        "statuss": "True",
        "ticket_Status_Desc": "Confirmed",
        "ticket_Status_Id": "0",
        "supplier_Refno": "SUP123",
        "transport_PNR": "PNR123",
        "paX_Details": [
            {
                "seat_Number": "A1",
                "status": "Confirmed",
                "ticket_Number": "TICKET001",
            },
            {
                "seat_Number": "A2",
                "status": "Confirmed",
                "ticket_Number": "TICKET002",
            },
        ],
    }

    result = BookingOrchestrator.requery_ticketing(
        db, "booking-001", "user-001", adapter
    )

    assert result["booking_status"] == BookingStatus.CONFIRMED
    assert result["supplier_refno"] == "SUP123"
    assert result["transport_pnr"] == "PNR123"

    # Verify that provider ticket numbers are stored against the correct seats.
    assert booking.passengers[0].ticket_number == "TICKET001"
    assert booking.passengers[1].ticket_number == "TICKET002"


def test_requery_mixed_passenger_statuses(monkeypatch):
    booking = mock_booking(BookingStatus.TICKETING_UNKNOWN)
    booking.temp_booking_ref = "MOCK12345"
    booking.passengers = [
        SimpleNamespace(id="p1", seat_number="A1", ticket_number=None),
        SimpleNamespace(id="p2", seat_number="A2", ticket_number=None),
    ]

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()
    adapter.BusRequery.return_value = {
        "response_Header": {"error_Code": "0000"},
        "statuss": "True",
        "ticket_Status_Desc": "Confirmed",
        "paX_Details": [
            {"seat_Number": "A1", "status": "Confirmed"},
            {"seat_Number": "A2", "status": "Payment Pending"},
        ],
    }

    result = BookingOrchestrator.requery_ticketing(
        db, "booking-001", "user-001", adapter
    )

    assert result["booking_status"] == BookingStatus.TICKETING_UNKNOWN
    assert booking.status == BookingStatus.TICKETING_UNKNOWN


def test_requery_timeout(monkeypatch):
    booking = mock_booking(BookingStatus.TICKETING_PENDING)
    booking.temp_booking_ref = "MOCK12345"

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()
    adapter.BusRequery.side_effect = TimeoutError("Provider timeout")

    result = BookingOrchestrator.requery_ticketing(
        db, "booking-001", "user-001", adapter
    )

    assert result["booking_status"] == BookingStatus.TICKETING_UNKNOWN
    assert db.commit.call_count == 1


def test_requery_rejects_invalid_booking_status(monkeypatch):
    booking = mock_booking(BookingStatus.PAYMENT_PENDING)
    booking.temp_booking_ref = "MOCK12345"

    setup_booking_repository(monkeypatch, booking)

    db = MagicMock()
    adapter = MagicMock()

    with pytest.raises(
        BookingOrchestrationError,
        match="Requery cannot run",
    ):
        BookingOrchestrator.requery_ticketing(
            db, "booking-001", "user-001", adapter
        )

    adapter.BusRequery.assert_not_called()
    db.commit.assert_not_called()


def test_end_to_end_booking_lifecycle(monkeypatch):
    # Shared in-memory booking repository for the complete flow.
    stored = {}

    repository = MagicMock()
    repository.save.side_effect = lambda booking: stored.update(
        {"booking": booking}
    )
    repository.get_by_id.side_effect = lambda booking_id: (
        stored.get("booking")
        if stored.get("booking")
        and stored["booking"].id == booking_id
        else None
    )

    monkeypatch.setattr(
        "Orchestrators.booking_orchestrator.BookingRepository",
        lambda db: repository,
    )

    request, seat_map_response = build_test_data()

    db = MagicMock()

    passenger_repository = MagicMock()
    passenger_repository.get_passengers.return_value = []

    adapter = MagicMock()

    # 1. Temporary booking succeeds.
    adapter.BusTempBooking.return_value = {
        "response_Header": {"error_Code": "0000"},
        "booking_RefNo": "E2E12345",
    }

    booking = BookingOrchestrator.start_booking(
        db=db,
        user_id="user-001",
        request=request,
        passenger_repository=passenger_repository,
        adapter=adapter,
        seat_map_response=seat_map_response,
        customer_mobile="9999999999",
        passenger_email="test@example.com",
    )

    assert booking.status == BookingStatus.TEMP_BOOKED
    assert booking.temp_booking_ref == "E2E12345"
    assert booking.total_amount == Decimal("838.96")

    # 2. Initiate payment.
    payment_service = MagicMock()

    payment_service.initiate_payment.return_value = {
        "payment_id": "payment-001",
        "payment_attempt_id": "attempt-001",
        "gateway_order_id": "order-001",
        "amount": "838.96",
        "currency": "INR",
        "status": "PENDING",
        "existing_attempt": False,
    }

    payment_result = BookingOrchestrator.initiate_booking_payment(
        db=db,
        booking_id=booking.id,
        user_id="user-001",
        payment_service=payment_service,
        customer={
            "name": "Test User",
            "email": "test@example.com",
        },
        idempotency_key=f"booking-payment:{booking.id}",
    )

    assert payment_result["status"] == "PENDING"
    assert booking.status == BookingStatus.PAYMENT_PENDING

    # 3. Verify payment.
    payment_service.payment_repository.get_by_id.return_value = (
        SimpleNamespace(
            id="payment-001",
            booking_id=booking.id,
        )
    )

    payment_service.verify_payment.return_value = {
        "payment_id": "payment-001",
        "gateway_payment_id": "gateway-payment-001",
        "status": "SUCCESS",
        "message": "Payment verified successfully",
    }

    verification_result = BookingOrchestrator.verify_booking_payment(
        db=db,
        booking_id=booking.id,
        user_id="user-001",
        payment_service=payment_service,
        payment_id="payment-001",
        gateway_payment_id="gateway-payment-001",
        signature="test-signature",
    )

    assert verification_result["status"] == "SUCCESS"
    assert booking.status == BookingStatus.PAYMENT_VERIFIED

    # 4. Ticketing request succeeds at the API level.
    # Final confirmation is deliberately deferred to BusRequery.
    adapter.BusTicketing.return_value = {
        "booking_RefNo": "E2E12345",
        "response_Header": {
            "error_Code": "0000",
            "error_Desc": "SUCCESS",
            "status_Id": "11",
        },
        "supplier_Refno": "SUP-E2E-001",
        "transport_PNR": "PNR-E2E-001",
        "statuss": "FALSE",
    }

    ticketing_result = BookingOrchestrator.complete_ticketing(
        db=db,
        booking_id=booking.id,
        user_id="user-001",
        adapter=adapter,
    )

    assert ticketing_result["booking_status"] == (
        BookingStatus.TICKETING_UNKNOWN
    )
    assert booking.status == BookingStatus.TICKETING_UNKNOWN

    # 5. Requery confirms the ticket and returns passenger ticket number.
    adapter.BusRequery.return_value = {
        "booking_RefNo": "E2E12345",
        "response_Header": {"error_Code": "0000"},
        "statuss": "True",
        "ticket_Status_Desc": "Confirmed",
        "supplier_Refno": "SUP-E2E-001",
        "transport_PNR": "PNR-E2E-001",
        "paX_Details": [
            {
                "seat_Number": "U1",
                "status": "Confirmed",
                "ticket_Number": "TICKET-E2E-001",
            }
        ],
    }

    requery_result = BookingOrchestrator.requery_ticketing(
        db=db,
        booking_id=booking.id,
        user_id="user-001",
        adapter=adapter,
    )

    # 6. Verify final persisted booking state.
    assert requery_result["booking_status"] == BookingStatus.CONFIRMED
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.supplier_refno == "SUP-E2E-001"
    assert booking.transport_pnr == "PNR-E2E-001"

    assert len(booking.passengers) == 1
    assert booking.passengers[0].seat_number == "U1"
    assert booking.passengers[0].ticket_number == "TICKET-E2E-001"

    adapter.BusTempBooking.assert_called_once()
    adapter.BusTicketing.assert_called_once_with({
        "booking_RefNo": "E2E12345",
    })
    adapter.BusRequery.assert_called_once_with({
        "booking_RefNo": "E2E12345",
    })

    payment_service.initiate_payment.assert_called_once()
    payment_service.verify_payment.assert_called_once()


def test_ticketing_timeout_then_requery_confirms_booking(monkeypatch):
    booking = SimpleNamespace(
        id="booking-timeout-001",
        user_id="user-001",
        status=BookingStatus.PAYMENT_VERIFIED,
        temp_booking_ref="TEMP-TIMEOUT-001",
        supplier_refno=None,
        transport_pnr=None,
        passengers=[
            SimpleNamespace(
                seat_number="U1",
                ticket_number=None,
            )
        ],
    )

    repository = MagicMock()
    repository.get_by_id.return_value = booking

    monkeypatch.setattr(
        "Orchestrators.booking_orchestrator.BookingRepository",
        lambda db: repository,
    )

    db = MagicMock()
    adapter = MagicMock()

    # Provider times out after receiving the ticketing request.
    adapter.BusTicketing.side_effect = TimeoutError(
        "AO Pay request timed out"
    )

    result = BookingOrchestrator.complete_ticketing(
        db=db,
        booking_id=booking.id,
        user_id=booking.user_id,
        adapter=adapter,
    )

    assert result["booking_status"] == BookingStatus.TICKETING_UNKNOWN
    assert booking.status == BookingStatus.TICKETING_UNKNOWN

    # Do not blindly retry ticketing.
    adapter.BusTicketing.assert_called_once()

    # Requery reveals that the ticket was actually issued.
    adapter.BusRequery.return_value = {
        "response_Header": {"error_Code": "0000"},
        "statuss": "True",
        "ticket_Status_Desc": "Confirmed",
        "supplier_Refno": "SUP-TIMEOUT-001",
        "transport_PNR": "PNR-TIMEOUT-001",
        "paX_Details": [
            {
                "seat_Number": "U1",
                "status": "Confirmed",
                "ticket_Number": "TICKET-TIMEOUT-001",
            }
        ],
    }

    requery_result = BookingOrchestrator.requery_ticketing(
        db=db,
        booking_id=booking.id,
        user_id=booking.user_id,
        adapter=adapter,
    )

    assert requery_result["booking_status"] == BookingStatus.CONFIRMED
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.supplier_refno == "SUP-TIMEOUT-001"
    assert booking.transport_pnr == "PNR-TIMEOUT-001"
    assert booking.passengers[0].ticket_number == "TICKET-TIMEOUT-001"

    # Ticketing was called only once; recovery used BusRequery.
    adapter.BusTicketing.assert_called_once()
    adapter.BusRequery.assert_called_once_with({
        "booking_RefNo": "TEMP-TIMEOUT-001",
    })


def test_failed_payment_prevents_ticketing(monkeypatch):
    booking = SimpleNamespace(
        id="booking-payment-fail-001",
        user_id="user-001",
        status=BookingStatus.PAYMENT_PENDING,
        temp_booking_ref="TEMP-001",
    )

    repository = MagicMock()
    repository.get_by_id.return_value = booking

    monkeypatch.setattr(
        "Orchestrators.booking_orchestrator.BookingRepository",
        lambda db: repository,
    )

    db = MagicMock()

    payment = SimpleNamespace(
        id="payment-001",
        booking_id=booking.id,
    )

    payment_service = MagicMock()
    payment_service.payment_repository.get_by_id.return_value = payment
    payment_service.verify_payment.return_value = {
        "payment_id": "payment-001",
        "status": "FAILED",
        "message": "Payment failed",
    }

    result = BookingOrchestrator.verify_booking_payment(
        db=db,
        booking_id=booking.id,
        user_id="user-001",
        payment_service=payment_service,
        payment_id="payment-001",
        gateway_payment_id="gateway-payment-001",
        signature="test-signature",
    )

    assert result["status"] == "FAILED"
    assert booking.status == BookingStatus.PAYMENT_PENDING

    adapter = MagicMock()

    with pytest.raises(BookingOrchestrationError):
        BookingOrchestrator.complete_ticketing(
            db=db,
            booking_id=booking.id,
            user_id="user-001",
            adapter=adapter,
        )

    adapter.BusTicketing.assert_not_called()

def test_start_booking_idempotent_retry_returns_existing_booking(monkeypatch):
    existing_booking = SimpleNamespace(
        id="booking-existing",
        user_id="user-001",
        status=BookingStatus.TEMP_BOOKED,
        temp_booking_ref="MOCK12345",
    )

    repository = MagicMock()
    repository.get_by_idempotency_key.return_value = existing_booking

    monkeypatch.setattr(
        "Orchestrators.booking_orchestrator.BookingRepository",
        lambda db: repository,
    )

    request, seat_map_response = build_test_data()
    request.idempotency_key = "stablebus-request-12345"

    db = MagicMock()
    passenger_repository = MagicMock()
    adapter = MagicMock()

    result = BookingOrchestrator.start_booking(
        db=db,
        user_id="user-001",
        request=request,
        passenger_repository=passenger_repository,
        adapter=adapter,
        seat_map_response=seat_map_response,
        customer_mobile="9999999999",
        passenger_email="test@example.com",
    )

    assert result is existing_booking
    assert result.id == "booking-existing"

    repository.get_by_idempotency_key.assert_called_once_with(
        user_id="user-001",
        idempotency_key="stablebus-request-12345",
    )

    passenger_repository.get_passengers.assert_not_called()
    adapter.BusTempBooking.assert_not_called()