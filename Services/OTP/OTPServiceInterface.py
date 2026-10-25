from abc import ABC, abstractmethod


class OTPInterface(ABC):

    @abstractmethod
    def send_otp(self, mobile_number: str, otp: str) -> bool:
        pass