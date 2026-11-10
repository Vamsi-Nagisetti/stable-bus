
from Adaptors.AOPayBusAPI.MockAOPayBookingAdaptee import MockAOPayAdaptee


def test_temp_booking_creates_reference():
    mock = MockAOPayAdaptee()

    response = mock.BusTempBooking(
        "/api/V1/Bus/Travel/BusTempBooking",
        {"request_Id": "REQ1", "bus_Key": "BUS1"},
    )

    assert response["response_Header"]["error_Code"] == "0000"
    assert response["booking_RefNo"]
    assert response["booking_RefNo"] in mock.bookings


def test_ticketing_confirms_temporary_booking():
    mock = MockAOPayAdaptee()

    temp_response = mock.BusTempBooking(
        "/api/V1/Bus/Travel/BusTempBooking",
        {"request_Id": "REQ1"},
    )

    booking_ref = temp_response["booking_RefNo"]

    response = mock.BusTicketing(
        "/api/V1/Bus/Travel/BusTicketing",
        {"request_Id": "REQ2", "booking_RefNo": booking_ref},
    )

    assert response["response_Header"]["error_Code"] == "0000"
    assert mock.bookings[booking_ref]["status"] == "CONFIRMED"


def test_requery_returns_booking_status():
    mock = MockAOPayAdaptee()

    temp_response = mock.BusTempBooking(
        "/api/V1/Bus/Travel/BusTempBooking",
        {"request_Id": "REQ1"},
    )

    booking_ref = temp_response["booking_RefNo"]

    response = mock.BusRequery(
        "/api/V1/Bus/Travel/BusRequery",
        {"request_Id": "REQ2", "booking_RefNo": booking_ref},
    )

    assert response["response_Header"]["error_Code"] == "0000"
    assert response["mock_status"] == "TEMP_BOOKED"


def test_ticketing_unknown_reference():
    mock = MockAOPayAdaptee()

    response = mock.BusTicketing(
        "/api/V1/Bus/Travel/BusTicketing",
        {"booking_RefNo": "INVALID"},
    )

    assert response["response_Header"]["error_Code"] == "MOCK404"


def test_requery_unknown_reference():
    mock = MockAOPayAdaptee()

    response = mock.BusRequery(
        "/api/V1/Bus/Travel/BusRequery",
        {"booking_RefNo": "INVALID"},
    )

    assert response["response_Header"]["error_Code"] == "MOCK404"
