class BookingManagement:

    def __init__(self, booking_repository: object, bus_api_adapter: object):
        self.booking_repository = booking_repository
        self.bus_api_adapter = bus_api_adapter

    def get_bookings(self, user_id: str):
        pass

    def hold_seat(self, user_id: str, trip_id: str, seat_ids: list[str]):
        pass

    def book_ticket(self, booking_id: str):
        pass

    def cancel_ticket(self, booking_id: str, user_id: str):
        pass