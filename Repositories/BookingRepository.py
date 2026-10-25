class BookingRepository:

    def __init__(self, database):
        self.database = database

    def save(self, booking):
        # INSERT booking record
        pass

    def get_by_id(self, booking_id):
        # SELECT booking by booking_id
        pass

    def get_by_user_id(self, user_id):
        # SELECT all bookings for a user
        pass

    def update_status(self, booking_id, status):
        # UPDATE booking status
        pass

    def delete_by_id(self, booking_id):
        # DELETE booking record, if appropriate
        pass