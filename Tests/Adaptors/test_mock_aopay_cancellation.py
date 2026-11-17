from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter
from Adaptors.AOPayBusAPI.MockAOPayBookingAdaptee import MockAOPayAdaptee


def make_adapter():
    mock = MockAOPayAdaptee()
    adapter = AOPayAdapter(
        adaptee=mock,
        registration_id="TEST_REG",
        ip_address="127.0.0.1",
        imei_number="TEST_IMEI",
    )
    return adapter, mock


def confirmed_booking(adapter):
    temp = adapter.BusTempBooking({
        "paX_Details": [
            {"name": "Test One", "seat_Number": "14"},
            {"name": "Test Two", "seat_Number": "5"},
        ],
        "from_City": "3",
        "to_City": "5",
        "travelDate": "20/11/2026",
    })
    ref = temp["booking_RefNo"]
    ticket = adapter.BusTicketing({"booking_RefNo": ref})
    requery = adapter.BusRequery({"booking_RefNo": ref})
    assert ticket["response_Header"]["error_Code"] == "0000"
    assert requery["mock_status"] == "CONFIRMED"
    return ref, requery["paX_Details"]


def test_mock_cancellation_quote_then_cancel():
    adapter, mock = make_adapter()
    ref, passengers = confirmed_booking(adapter)
    passenger = passengers[0]
    ticket = {
        "seat_Number": str(passenger["seat_Number"]),
        "ticket_Number": passenger["ticket_Number"],
        "transport_PNR": passenger["transport_PNR"],
    }

    quote = adapter.BusCancellationCharges({
        "booking_RefNo": ref,
        "cancelTicket_Details": [ticket],
    })
    assert quote["response_Header"]["error_Code"] == "0000"
    assert quote["cancellable"] == "true"
    assert quote["cancellationPenaltyValues"][0]["cancellation_Penalty"] == "10"

    cancelled = adapter.BusCancellation({
        "booking_RefNo": ref,
        "busTicketstoCancel": [ticket],
        "cancellationCharge_Key": quote["cancellationCharge_Key"],
    })
    assert cancelled["response_Header"]["error_Code"] == "0000"
    assert cancelled["statuss"] == "True"
    assert mock.bookings[ref]["passengers"][0]["status"] == "Cancelled"
    assert mock.bookings[ref]["status"] == "CONFIRMED"  # partial cancellation


def test_mock_cancellation_key_is_single_use():
    adapter, _ = make_adapter()
    ref, passengers = confirmed_booking(adapter)
    passenger = passengers[0]
    ticket = {
        "seat_Number": str(passenger["seat_Number"]),
        "ticket_Number": passenger["ticket_Number"],
        "transport_PNR": passenger["transport_PNR"],
    }
    quote = adapter.BusCancellationCharges({"booking_RefNo": ref, "cancelTicket_Details": [ticket]})
    payload = {
        "booking_RefNo": ref,
        "busTicketstoCancel": [ticket],
        "cancellationCharge_Key": quote["cancellationCharge_Key"],
    }
    first = adapter.BusCancellation(payload)
    second = adapter.BusCancellation(payload)
    assert first["statuss"] == "True"
    assert second["statuss"] == "False"


def test_mock_provider_history_contains_confirmed_booking():
    adapter, _ = make_adapter()
    ref, _ = confirmed_booking(adapter)
    history = adapter.BusHistory({"fromdate": "01/11/2026", "month": "11", "todate": "30/11/2026", "type": 0, "year": "2026"})
    assert history["response_Header"]["error_Code"] == "0000"
    assert any(item["booking_RefNo"] == ref for item in history["busAvailableBookings"])


def test_mock_full_cancellation_marks_booking_cancelled():
    adapter, mock = make_adapter()
    ref, passengers = confirmed_booking(adapter)
    tickets = [
        {
            "seat_Number": str(p["seat_Number"]),
            "ticket_Number": p["ticket_Number"],
            "transport_PNR": p["transport_PNR"],
        }
        for p in passengers
    ]
    quote = adapter.BusCancellationCharges({
        "booking_RefNo": ref,
        "cancelTicket_Details": tickets,
    })
    result = adapter.BusCancellation({
        "booking_RefNo": ref,
        "busTicketstoCancel": tickets,
        "cancellationCharge_Key": quote["cancellationCharge_Key"],
    })
    assert result["statuss"] == "True"
    assert mock.bookings[ref]["status"] == "CANCELLED"


def test_mock_history_type_one_returns_cancelled_tickets():
    adapter, _ = make_adapter()
    ref, passengers = confirmed_booking(adapter)
    passenger = passengers[0]
    ticket = {
        "seat_Number": str(passenger["seat_Number"]),
        "ticket_Number": passenger["ticket_Number"],
        "transport_PNR": passenger["transport_PNR"],
    }
    quote = adapter.BusCancellationCharges({"booking_RefNo": ref, "cancelTicket_Details": [ticket]})
    adapter.BusCancellation({
        "booking_RefNo": ref,
        "busTicketstoCancel": [ticket],
        "cancellationCharge_Key": quote["cancellationCharge_Key"],
    })
    history = adapter.BusHistory({"type": 1})
    assert any(item["booking_RefNo"] == ref for item in history["busAvailableBookings"])
