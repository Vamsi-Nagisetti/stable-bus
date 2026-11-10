from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter
from Adaptors.AOPayBusAPI.MockAOPayBookingAdaptee import MockAOPayAdaptee


def create_adapter():
    mock = MockAOPayAdaptee()

    adapter = AOPayAdapter(
        adaptee=mock,
        registration_id="TEST_REG",
        ip_address="127.0.0.1",
        imei_number="TEST_IMEI",
    )

    return adapter, mock


def test_complete_mock_booking_flow():
    adapter, mock = create_adapter()

    # 1. Temporary booking
    temp_response = adapter.BusTempBooking({
        "sample_provider_field": "temp-value",
    })

    assert temp_response["response_Header"]["error_Code"] == "0000"

    booking_ref = temp_response["booking_RefNo"]

    # 2. Ticketing
    ticket_response = adapter.BusTicketing({
        "booking_RefNo": booking_ref,
    })

    assert ticket_response["response_Header"]["error_Code"] == "0000"

    # 3. Requery
    requery_response = adapter.BusRequery({
        "booking_RefNo": booking_ref,
    })

    assert requery_response["response_Header"]["error_Code"] == "0000"
    assert requery_response["mock_status"] == "CONFIRMED"

    assert mock.bookings[booking_ref]["status"] == "CONFIRMED"