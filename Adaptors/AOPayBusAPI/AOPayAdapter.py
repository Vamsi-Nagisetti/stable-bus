from Adaptors.AOPayBusAPI.BusAPIBaseAdaptor import BusAPIBaseAdaptor
from uuid import uuid4

class AOPayAdapter(BusAPIBaseAdaptor):

    def __init__(
        self,
        adaptee,
        registration_id,
        ip_address,
        imei_number,
    ):
        self.adaptee = adaptee
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

    def BusTempBooking(self, trip_id, seat_ids, passengers):
        payload = self._common_payload()

        payload.update({
            # Map trip_id, seat_ids and passengers to AO Pay's
            # documented temporary-booking request fields.
        })

        return self.adaptee.BusTempBooking(
            "REPLACE_WITH_DOCUMENTED_TEMP_BOOKING_ENDPOINT",
            payload,
        )

    def BusTicketing(self, booking_id, payment_reference):
        payload = self._common_payload()

        payload.update({
            # Map booking_id and payment_reference to the
            # actual ticketing fields required by AO Pay.
        })

        return self.adaptee.BusTicketing(
            "REPLACE_WITH_DOCUMENTED_TICKETING_ENDPOINT",
            payload,
        )

    def BusRequery(self, booking_id):
        payload = self._common_payload()

        payload.update({
            # Map booking_id to AO Pay's required requery fields.
        })

        return self.adaptee.BusRequery(
            "REPLACE_WITH_DOCUMENTED_REQUERY_ENDPOINT",
            payload,
        )