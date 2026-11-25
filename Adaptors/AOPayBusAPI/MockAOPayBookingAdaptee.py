
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("stablebus.mock_aopay")


class MockAOPayAdaptee:

    def __init__(self):
        self.bookings = {}
        self.cancellation_keys = {}

    @staticmethod
    def _response_header(request_id="MOCK"):
        return {
            "error_Code": "0000",
            "error_Desc": "SUCCESS",
            "error_InnerException": "",
            "request_Id": request_id,
        }

    def BusTempBooking(self, endpoint: str, payload: dict) -> dict:
        booking_ref = f"MOCK{uuid.uuid4().hex[:8].upper()}"

        self.bookings[booking_ref] = {
            "booking_RefNo": booking_ref,
            "status": "TEMP_BOOKED",
            "payload": dict(payload),
            "created_at": datetime.now(timezone.utc),
            "supplier_Refno": None,
            "transport_PNR": None,
            "passengers": [],
        }

        logger.info(
            "Mock temporary booking created: %s",
            booking_ref,
        )

        return {
            "response_Header": self._response_header(
                payload.get("request_Id", "MOCK")
            ),
            "booking_RefNo": booking_ref,
        }

    def BusTicketing(self, endpoint: str, payload: dict) -> dict:
        booking_ref = payload.get("booking_RefNo")
        booking = self.bookings.get(booking_ref)

        if not booking:
            return {
                "response_Header": {
                    "error_Code": "MOCK404",
                    "error_Desc": "Booking reference not found",
                    "error_InnerException": "",
                    "request_Id": payload.get("request_Id", "MOCK"),
                },
                "booking_RefNo": booking_ref,
            }

        supplier_ref = f"SUP{uuid.uuid4().hex[:10].upper()}"
        transport_pnr = f"PNR{uuid.uuid4().hex[:8].upper()}"

        passengers = []

        original_passengers = (
            booking["payload"].get("paX_Details") or []
        )

        for passenger in original_passengers:
            passengers.append({
                **passenger,
                "seat_Number": passenger.get("seat_Number"),
                "ticket_Number": (
                    f"TKT{uuid.uuid4().hex[:10].upper()}"
                ),
                "status": "Confirmed",
                "transport_PNR": transport_pnr,
            })

        booking["status"] = "CONFIRMED"
        booking["supplier_Refno"] = supplier_ref
        booking["transport_PNR"] = transport_pnr
        booking["passengers"] = passengers

        logger.info(
            "Mock ticketing completed: %s",
            booking_ref,
        )

        return {
            "response_Header": self._response_header(
                payload.get("request_Id", "MOCK")
            ),
            "booking_RefNo": booking_ref,
            "supplier_Refno": supplier_ref,
            "transport_PNR": transport_pnr,
        }

    def BusRequery(self, endpoint: str, payload: dict) -> dict:
        booking_ref = payload.get("booking_RefNo")
        booking = self.bookings.get(booking_ref)

        if not booking:
            return {
                "response_Header": {
                    "error_Code": "MOCK404",
                    "error_Desc": "Booking reference not found",
                    "error_InnerException": "",
                    "request_Id": payload.get("request_Id", "MOCK"),
                },
                "booking_RefNo": booking_ref,
            }

        confirmed = booking["status"] == "CONFIRMED"

        return {
            "response_Header": self._response_header(
                payload.get("request_Id", "MOCK")
            ),
            "booking_RefNo": booking_ref,
            "supplier_Refno": booking["supplier_Refno"],
            "transport_PNR": booking["transport_PNR"],
            "statuss": confirmed,
            "ticket_Status_Desc": (
                "Confirmed" if confirmed else "Pending"
            ),
            "ticket_Status_Id": "0" if confirmed else "1",
            "paX_Details": booking["passengers"],
            "mock_status": booking["status"],
        }


    def BusCancellationCharges(self, payload: dict) -> dict:
        booking_ref = payload.get("booking_RefNo")
        booking = self.bookings.get(booking_ref)
        request_id = payload.get("request_Id", "MOCK")
        tickets = payload.get("cancelTicket_Details") or []

        if not booking or booking.get("status") != "CONFIRMED":
            return {
                "cancellable": "false",
                "cancellationCharge_Key": "",
                "cancellationPenaltyValues": [],
                "response_Header": {
                    **self._response_header(request_id),
                    "error_Code": "MOCK404",
                    "error_Desc": "Confirmed booking not found",
                },
                "statuss": "False",
                "message": "Booking is not cancellable",
                "value": "",
            }

        known = {str(p.get("ticket_Number")): p for p in booking["passengers"]}
        penalties = []
        for ticket in tickets:
            passenger = known.get(str(ticket.get("ticket_Number")))
            if (passenger and passenger.get("status") != "Cancelled"
                    and str(passenger.get("seat_Number")) == str(ticket.get("seat_Number"))):
                penalties.append({
                    "cancellation_Penalty": "10",
                    "seat_Number": str(ticket.get("seat_Number")),
                    "ticket_Number": ticket.get("ticket_Number"),
                })

        if not penalties or len(penalties) != len(tickets):
            return {
                "cancellable": "false",
                "cancellationCharge_Key": "",
                "cancellationPenaltyValues": penalties,
                "response_Header": {
                    **self._response_header(request_id),
                    "error_Code": "MOCK400",
                    "error_Desc": "One or more tickets do not belong to this booking",
                },
                "statuss": "False",
                "message": "Invalid ticket selection",
                "value": "",
            }

        charge_key = f"MOCK-CANCEL-{uuid.uuid4().hex}"
        self.cancellation_keys[charge_key] = {
            "booking_ref": booking_ref,
            "tickets": penalties,
        }
        return {
            "cancellable": "true",
            "cancellationCharge_Key": charge_key,
            "cancellationPenaltyValues": penalties,
            "response_Header": self._response_header(request_id),
            "serviceCharge": "0",
            "statuss": "True",
            "message": "Transaction successfully",
            "value": "",
        }

    def BusCancellation(self, payload: dict) -> dict:
        request_id = payload.get("request_Id", "MOCK")
        charge_key = payload.get("cancellationCharge_Key")
        context = self.cancellation_keys.pop(charge_key, None)
        if not context or context["booking_ref"] != payload.get("booking_RefNo"):
            return {
                "cancellationPenaltyValues": [],
                "response_Header": {
                    **self._response_header(request_id),
                    "error_Code": "MOCK409",
                    "error_Desc": "Invalid or expired cancellation key",
                },
                "statuss": "False",
                "message": "Cancellation key is invalid or already used",
                "value": "",
            }

        booking = self.bookings[context["booking_ref"]]
        requested = {str(x.get("ticket_Number")) for x in payload.get("busTicketstoCancel", [])}
        authorized = {str(x.get("ticket_Number")) for x in context["tickets"]}
        if requested != authorized:
            return {
                "cancellationPenaltyValues": [],
                "response_Header": {
                    **self._response_header(request_id),
                    "error_Code": "MOCK400",
                    "error_Desc": "Cancellation ticket list differs from charge request",
                },
                "statuss": "False",
                "message": "Ticket selection mismatch",
                "value": "",
            }

        for passenger in booking["passengers"]:
            if str(passenger.get("ticket_Number")) in requested:
                passenger["status"] = "Cancelled"
        if all(p.get("status") == "Cancelled" for p in booking["passengers"]):
            booking["status"] = "CANCELLED"
        return {
            "cancellationPenaltyValues": context["tickets"],
            "response_Header": self._response_header(request_id),
            "statuss": "True",
            "message": "Transaction successfully",
            "value": "",
        }

    def BusHistory(self, payload: dict) -> dict:
        request_id = payload.get("request_Id", "MOCK")
        items = []
        requested_type = int(payload.get("type", 0))
        for booking in self.bookings.values():
            if booking.get("status") not in {"CONFIRMED", "CANCELLED"}:
                continue
            has_cancelled_seats = any(
                passenger.get("status") == "Cancelled"
                for passenger in booking.get("passengers", [])
            )
            if requested_type == 1 and not has_cancelled_seats:
                continue
            if requested_type == 0 and booking.get("status") == "CANCELLED":
                continue
            original = booking.get("payload", {})
            status_desc = (
                "Cancelled" if booking.get("status") == "CANCELLED"
                else "Partially Cancelled" if has_cancelled_seats
                else "Confirmed"
            )
            items.append({
                "booking_RefNo": booking["booking_RefNo"],
                "cancellationCharges": 0,
                "customerMobile": original.get("customer_Mobile", ""),
                "from_City": original.get("from_City", ""),
                "gatewayCharges": 0,
                "invoiceNumber": "MOCK-INVOICE",
                "operator_Name": "Mock Operator",
                "paX_Name": (booking.get("passengers") or [{}])[0].get("name", "Mock Passenger"),
                "statusDesc": status_desc,
                "ticketingDate": booking["created_at"].strftime("%d/%m/%Y %H:%M:%S"),
                "to_City": original.get("to_City", ""),
                "total_Amount": 0,
                "transport_PNR": booking.get("transport_PNR", ""),
                "travelDate": original.get("travelDate", ""),
            })
        return {
            "busAvailableBookings": items,
            "response_Header": self._response_header(request_id),
            "statuss": "True",
            "message": "Transaction successfully",
            "value": "",
        }
