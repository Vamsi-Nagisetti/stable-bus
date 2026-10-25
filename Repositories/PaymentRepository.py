class PaymentRepository:

    def __init__(self, database):
        self.database = database

    def save(self, payment):
        # INSERT payment record
        pass

    def update_status(self, payment_id, status):
        # UPDATE payment record
        pass

    def get_by_id(self, payment_id):
        # SELECT payment record
        pass