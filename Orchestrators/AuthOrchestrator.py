
import logging

from Management.OtpMangement import OTPManagement, OTPDeliveryError
from Management.RateLimitManagement import RateLimitManagement

logger = logging.getLogger("stablebus.management.auth")


class AuthOrchestrator:

    def __init__(
        self,
        otp_management: OTPManagement,
        rate_limit_management: RateLimitManagement
    ):
        self.otp_management = otp_management
        self.rate_limit_management = rate_limit_management

    def send_otp(self, mobile_number: str, client_ip: str) -> bool:

        self.rate_limit_management.check_otp_request(
            mobile_number,
            client_ip
        )

        try:
            self.otp_management.send_otp(mobile_number)

        except OTPDeliveryError:
            try:
                self.rate_limit_management.clear_otp_cooldown(
                    mobile_number
                )
            except Exception:
                logger.exception(
                    "Failed to clear OTP cooldown after delivery failure"
                )

            logger.exception("OTP delivery failed")
            raise

        logger.info("OTP delivery completed successfully")
        return True
