
import json

from Management.OtpMangement import OTPManagement
from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor


class MockOTPService:
    def __init__(self):
        self.sent_mobile = None
        self.sent_otp = None

    def send_otp(self, mobile_number: str, otp: str) -> bool:
        self.sent_mobile = mobile_number
        self.sent_otp = otp
        return True


otp_service = MockOTPService()
adaptee = RedisCacheAdaptee()
cache = RedisCacheAdaptor(adaptee)

otp_management = OTPManagement(otp_service, cache)

try:
    
    mobile_number = "9390944905"

    # Test 1: Request an OTP
    otp_management.send_otp(mobile_number)
    correct_otp = otp_service.sent_otp

    print("OTP requested successfully")

    # Test 2: Wrong OTP should fail
    result = otp_management.verify_otp(mobile_number, "000000")
    print("Wrong OTP rejected:", result is False)

    # Test 3: Correct OTP should work after one wrong attempt
    result = otp_management.verify_otp(mobile_number, correct_otp)
    print("Correct OTP accepted:", result is True)

    # Test 4: OTP must not be reusable
    result = otp_management.verify_otp(mobile_number, correct_otp)
    print("Reused OTP rejected:", result is False)

    otp_management.send_otp(mobile_number)
    correct_otp = otp_service.sent_otp

    wrong_otp = "000000"
    if wrong_otp == correct_otp:
        wrong_otp = "000001"

    for attempt in range(1, 6):
        result = otp_management.verify_otp(mobile_number, wrong_otp)
        print(f"Wrong attempt {attempt} rejected:", result is False)

    # Even the correct OTP must now fail
    result = otp_management.verify_otp(mobile_number, correct_otp)
    print("Correct OTP rejected after five failures:", result is False)
    otp_management.send_otp(mobile_number)
    correct_otp = otp_service.sent_otp

    key = otp_management._get_otp_key(mobile_number)

    # Simulate expiry
    cache.delete(key)

    result = otp_management.verify_otp(mobile_number, correct_otp)

    print("Expired/missing OTP rejected:", result is False)


finally:
    cache.delete("stablebus:otp:9390944905")
    adaptee.close()
