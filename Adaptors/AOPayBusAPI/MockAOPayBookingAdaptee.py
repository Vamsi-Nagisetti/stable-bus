
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("stablebus.mock_aopay")


class MockAOPayAdaptee:

    def __init__(self):
        self.bookings = {}

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
        }
