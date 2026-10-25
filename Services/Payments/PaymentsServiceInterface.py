from abc import ABC,abstractmethod

class PaymentServiceInterface(ABC):

  
    
    @abstractmethod
    def initiate_payment(self, booking_id: str):
        pass
    
    @abstractmethod
    def verify_payment(self, payment_id: str):
        pass

    @abstractmethod
    def refund_payment(self, payment_id: str):
        pass