from unittest.mock import MagicMock

from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter


def create_adapter():
    adaptee = MagicMock()

    adapter = AOPayAdapter(
        adaptee=adaptee,
        registration_id="TEST_REG",
        ip_address="127.0.0.1",
        imei_number="TEST_IMEI",
    )

    return adapter, adaptee


def assert_common_payload(payload):
    assert payload["registrationID"] == "TEST_REG"
    assert payload["iP_Address"] == "127.0.0.1"
    assert payload["imeI_Number"] == "TEST_IMEI"
    assert payload["request_Id"]


def test_bus_temp_booking():
    adapter, adaptee = create_adapter()
    request = {"bus_Key": "BUS123"}

    adapter.BusTempBooking(request)

    endpoint, payload = adaptee.BusTempBooking.call_args.args

    assert endpoint == "/api/V1/Bus/Travel/BusTempBooking"
    assert payload["bus_Key"] == "BUS123"
    assert_common_payload(payload)


def test_bus_ticketing():
    adapter, adaptee = create_adapter()
    request = {"temp_Booking_Id": "TEMP123"}

    adapter.BusTicketing(request)

    endpoint, payload = adaptee.BusTicketing.call_args.args

    assert endpoint == "/api/V1/Bus/Travel/BusTicketing"
    assert payload["temp_Booking_Id"] == "TEMP123"
    assert_common_payload(payload)


def test_bus_requery():
    adapter, adaptee = create_adapter()
    request = {"booking_Ref": "BOOK123"}

    adapter.BusRequery(request)

    endpoint, payload = adaptee.BusRequery.call_args.args

    assert endpoint == "/api/V1/Bus/Travel/BusRequery"
    assert payload["booking_Ref"] == "BOOK123"
    assert_common_payload(payload)