from Repositories.UserRepository import UserRepository
from Services.OTP import FAST2SMS_OTP_Service
from core.database import SessionLocal
from models.User import User

# db = SessionLocal()
# user_repo = UserRepository(db)

# saved_user = user_repo.get_by_id(1)
# print(saved_user.mobile_number if saved_user else "User not found")

from Services.OTP.FAST2SMS_OTP_Service import Fast2SMSOTPService

otp_service = Fast2SMSOTPService()
otp_service.send_otp("9390944905")  # Replace with a valid mobile number
