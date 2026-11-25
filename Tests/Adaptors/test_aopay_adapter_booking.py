
from unittest.mock import MagicMock

from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter


def create_adapter():
    adaptee = MagicMock()
    booking_adaptee = MagicMock()

    adapter = AOPayAdapter(
        adaptee=adaptee,
        booking_adaptee=booking_adaptee,
        registration_id="TEST_REG",
        ip_address="127.0.0.1",
        imei_number="TEST_IMEI",
    )

    return adapter, adaptee, booking_adaptee


def assert_common_payload(payload):
    assert payload["registrationID"] == "TEST_REG"
    assert payload["iP_Address"] == "127.0.0.1"
    assert payload["imeI_Number"] == "TEST_IMEI"
    assert payload["request_Id"]


def test_bus_temp_booking():
    adapter, _, booking_adaptee = create_adapter()
    request = {"sample_field": "temp-value"}

    adapter.BusTempBooking(request)

    endpoint, payload = (
        booking_adaptee.BusTempBooking.call_args.args
    )

    assert endpoint == "/api/V1/Bus/Travel/BusTempBooking"
    assert payload["sample_field"] == "temp-value"
    assert_common_payload(payload)


def test_bus_ticketing():
    adapter, _, booking_adaptee = create_adapter()
    request = {"sample_field": "ticket-value"}

    adapter.BusTicketing(request)

    endpoint, payload = (
        booking_adaptee.BusTicketing.call_args.args
    )

    assert endpoint == "/api/V1/Bus/Travel/BusTicketing"
    assert payload["sample_field"] == "ticket-value"
    assert_common_payload(payload)


def test_bus_requery():
    adapter, _, booking_adaptee = create_adapter()
    request = {"sample_field": "requery-value"}

    adapter.BusRequery(request)

    endpoint, payload = (
        booking_adaptee.BusRequery.call_args.args
    )

    assert endpoint == "/api/V1/Bus/Travel/BusRequery"
    assert payload["sample_field"] == "requery-value"
    assert_common_payload(payload)


def test_booking_calls_use_separate_booking_adaptee():
    adapter, real_adaptee, booking_adaptee = create_adapter()

    adapter.BusTempBooking({"sample_field": "value"})

    booking_adaptee.BusTempBooking.assert_called_once()
    real_adaptee.BusTempBooking.assert_not_called()


def test_original_payload_is_not_modified():
    adapter, _, _ = create_adapter()

    request = {"sample_field": "value"}
    original = request.copy()

    adapter.BusTempBooking(request)

    assert request == original
