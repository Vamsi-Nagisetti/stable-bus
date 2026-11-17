
import pytest

from Adaptors.AOPayBusAPI.MockAOPayBookingAdaptee import (
    MockAOPayAdaptee,
)


@pytest.fixture
def adapter():
    return MockAOPayAdaptee()


@pytest.fixture
def passenger_payload():
    return {
        "request_Id": "TEST123",
        "paX_Details": [
            {
                "seat_Number": "1",
                "passenger_Name": "Test Passenger",
                "passenger_Gender": 0,
            },
            {
                "seat_Number": "2",
                "passenger_Name": "Test Passenger 2",
                "passenger_Gender": 1,
            },
        ],
    }


def create_temp_booking(adapter, passenger_payload):
    return adapter.BusTempBooking(
        "/api/V1/Bus/Travel/BusTempBooking",
        passenger_payload,
    )


def test_temporary_booking_success(adapter, passenger_payload):
    response = create_temp_booking(adapter, passenger_payload)

    assert response["response_Header"]["error_Code"] == "0000"
    assert response["booking_RefNo"].startswith("MOCK")

    assert response["booking_RefNo"] in adapter.bookings


def test_ticketing_success(adapter, passenger_payload):
    temp_response = create_temp_booking(adapter, passenger_payload)
    booking_ref = temp_response["booking_RefNo"]

    response = adapter.BusTicketing(
        "/api/V1/Bus/Travel/BusTicketing",
        {"booking_RefNo": booking_ref},
    )

    assert response["response_Header"]["error_Code"] == "0000"
    assert response["booking_RefNo"] == booking_ref
    assert response["supplier_Refno"].startswith("SUP")
    assert response["transport_PNR"].startswith("PNR")


def test_ticketing_with_invalid_booking_reference(adapter):
    response = adapter.BusTicketing(
        "/api/V1/Bus/Travel/BusTicketing",
        {"booking_RefNo": "INVALID"},
    )

    assert response["response_Header"]["error_Code"] == "MOCK404"


def test_requery_returns_confirmed_ticket(adapter, passenger_payload):
    temp_response = create_temp_booking(adapter, passenger_payload)
    booking_ref = temp_response["booking_RefNo"]

    adapter.BusTicketing(
        "/api/V1/Bus/Travel/BusTicketing",
        {"booking_RefNo": booking_ref},
    )

    response = adapter.BusRequery(
        "/api/V1/Bus/Travel/BusRequery",
        {"booking_RefNo": booking_ref},
    )

    assert response["response_Header"]["error_Code"] == "0000"
    assert response["statuss"] is True
    assert response["ticket_Status_Desc"] == "Confirmed"
    assert len(response["paX_Details"]) == 2

    for passenger in response["paX_Details"]:
        assert passenger["seat_Number"]
        assert passenger["ticket_Number"].startswith("TKT")
        assert passenger["status"] == "Confirmed"


def test_requery_before_ticketing_returns_pending(adapter, passenger_payload):
    temp_response = create_temp_booking(adapter, passenger_payload)
    booking_ref = temp_response["booking_RefNo"]

    response = adapter.BusRequery(
        "/api/V1/Bus/Travel/BusRequery",
        {"booking_RefNo": booking_ref},
    )

    assert response["response_Header"]["error_Code"] == "0000"
    assert response["statuss"] is False
    assert response["ticket_Status_Desc"] == "Pending"


def test_requery_with_invalid_booking_reference(adapter):
    response = adapter.BusRequery(
        "/api/V1/Bus/Travel/BusRequery",
        {"booking_RefNo": "INVALID"},
    )

    assert response["response_Header"]["error_Code"] == "MOCK404"
