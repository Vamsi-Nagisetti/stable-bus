import os
import requests
from dotenv import load_dotenv
import secrets
import re

from Services.OTP.OTPServiceInterface import OTPInterface

load_dotenv()


class Fast2SMSOTPService(OTPInterface):

    def __init__(self):
        self.api_key = os.getenv("FAST2SMS_API_KEY")

        if not self.api_key:
            raise RuntimeError("FAST2SMS_API_KEY is missing")

        self.url = "https://www.fast2sms.com/dev/bulkV2"

    def send_otp(self, mobile_number: str, otp: str) -> bool:
        if not re.fullmatch(r"[6-9]\d{9}", mobile_number):
            raise ValueError("Invalid Indian mobile number")

        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP must contain exactly six digits")

        payload = {
            "variables_values": otp,
            "route": "otp",
            "numbers": mobile_number,
        }

        headers = {
            "authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = requests.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()

        except requests.RequestException as exc:
            raise RuntimeError(
                "Failed to send OTP through Fast2SMS"
            ) from exc

        if not result.get("return"):
            raise RuntimeError("Fast2SMS rejected the OTP request")

        return True

    def validate_otp(self, mobile_number: str, otp: str):
        # TODO: implement this
        pass