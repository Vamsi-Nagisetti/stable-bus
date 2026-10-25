from abc import ABC, abstractmethod


class BusAPIBaseAdaptor(ABC):

    @abstractmethod
    def BusSearch(self, from_city: str, to_city: str, travel_date: str):
        pass

    @abstractmethod
    def BusCityList(self):
        pass

    @abstractmethod
    def BusSeatMap(self, trip_id: str):
        pass

    @abstractmethod
    def BusTempBooking(self, trip_id: str, seat_ids: list[str], passengers: list[dict]):
        pass

    @abstractmethod
    def BusTicketing(self, booking_id: str, payment_reference: str):
        pass

    @abstractmethod
    def BusRequery(self, booking_id: str):
        pass