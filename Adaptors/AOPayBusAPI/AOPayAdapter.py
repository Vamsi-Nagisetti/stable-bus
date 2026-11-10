from Adaptors.AOPayBusAPI.BusAPIBaseAdaptor import BusAPIBaseAdaptor
from uuid import uuid4

class AOPayAdapter(BusAPIBaseAdaptor):

    def __init__(
        self,
        adaptee,
        registration_id,
        ip_address,
        imei_number,
        booking_adaptee=None
    ):
        self.adaptee = adaptee
        self.booking_adaptee = booking_adaptee or adaptee
        self.registration_id = registration_id
        self.ip_address = ip_address
        self.imei_number = imei_number

    def _common_payload(self):
        return {
            "iP_Address": self.ip_address,
            "request_Id": str(uuid4()),
            "imeI_Number": self.imei_number,
            "registrationID": self.registration_id,
        }

    def _booking_payload(self, payload: dict) -> dict:
        request_payload = dict(payload)
        request_payload.update(self._common_payload())
        return request_payload

    def BusSearch(self, from_city, to_city, travel_date):
        payload = self._common_payload()

        payload.update({
            "from_City": from_city,
            "to_City": to_city,
            "travelDate": travel_date,
        })

        return self.adaptee.BusSearch(payload)

    def BusCityList(self):
        payload = self._common_payload()
        return self.adaptee.BusCityList(payload)

    def BusSeatMap(
            self,
            bus_key,
            search_key,
            boarding_id,
            dropping_id,
        ):
        payload = self._common_payload()

        payload.update({
            "bus_Key": bus_key,
            "search_Key": search_key,
            "boarding_Id": boarding_id,
            "dropping_Id": dropping_id,
        })

        return self.adaptee.BusSeatMap(
            "/api/V1/Bus/Travel/BusSeatMap",
            payload,
        )


    def BusTempBooking(self, payload: dict) -> dict:
        return self.booking_adaptee.BusTempBooking(
            "/api/V1/Bus/Travel/BusTempBooking",
            self._booking_payload(payload),
        )


    def BusTicketing(self, payload: dict) -> dict:
        return self.booking_adaptee.BusTicketing(
            "/api/V1/Bus/Travel/BusTicketing",
            self._booking_payload(payload),
        )


    def BusRequery(self, payload: dict) -> dict:
        return self.booking_adaptee.BusRequery(
            "/api/V1/Bus/Travel/BusRequery",
            self._booking_payload(payload),
        )