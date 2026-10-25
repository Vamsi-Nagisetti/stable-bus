from Services.Payments.PaymentsServiceInterface import PaymentServiceInterface

class PaymentService(PaymentServiceInterface):

    def __init__(self, payment_provider: object, payment_repository: object):
        self.payment_provider = payment_provider
        self.payment_repository = payment_repository

    def initiate_payment(self, booking_id: str):
        pass

    def verify_payment(self, payment_id: str):
        pass

    def refund_payment(self, payment_id: str):
        pass