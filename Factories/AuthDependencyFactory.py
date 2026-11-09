
from Adaptors.Cache.CacheBaseAdaptor import CacheBaseAdaptor
from Services.OTP.OTPServiceInterface import OTPInterface

from Management.OtpMangement import OTPManagement
from Management.RateLimitManagement import RateLimitManagement

from Orchestrators.AuthOrchestrator import AuthOrchestrator


class AuthDependencyFactory:
    """
    Factory responsible for constructing authentication dependencies.

    Infrastructure implementations such as Redis and Fast2SMS
    are injected from outside.
    """

    def __init__(
        self,
        cache: CacheBaseAdaptor,
        otp_service: OTPInterface
    ):
        self.cache = cache
        self.otp_service = otp_service

        self.otp_management = OTPManagement(
            otp_service=self.otp_service,
            cache=self.cache
        )

        self.rate_limit_management = RateLimitManagement(
            cache=self.cache
        )

        self.auth_orchestrator = AuthOrchestrator(
            otp_management=self.otp_management,
            rate_limit_management=self.rate_limit_management
        )

    def get_auth_orchestrator(self) -> AuthOrchestrator:
        return self.auth_orchestrator
