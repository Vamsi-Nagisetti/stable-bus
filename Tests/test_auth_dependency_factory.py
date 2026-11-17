
from unittest.mock import Mock

from Factories.AuthDependencyFactory import AuthDependencyFactory
from Adaptors.Cache.CacheBaseAdaptor import CacheBaseAdaptor
from Services.OTP.OTPServiceInterface import OTPInterface
from Orchestrators.AuthOrchestrator import AuthOrchestrator


def test_factory_creates_auth_orchestrator():
    cache = Mock(spec=CacheBaseAdaptor)
    otp_service = Mock(spec=OTPInterface)

    factory = AuthDependencyFactory(
        cache=cache,
        otp_service=otp_service
    )

    assert isinstance(factory.get_auth_orchestrator(), AuthOrchestrator)


def test_factory_injects_same_cache_into_management_classes():
    cache = Mock(spec=CacheBaseAdaptor)
    otp_service = Mock(spec=OTPInterface)

    factory = AuthDependencyFactory(
        cache=cache,
        otp_service=otp_service
    )

    assert factory.otp_management.cache is cache
    assert factory.rate_limit_management.cache is cache


def test_factory_injects_otp_service():
    cache = Mock(spec=CacheBaseAdaptor)
    otp_service = Mock(spec=OTPInterface)

    factory = AuthDependencyFactory(
        cache=cache,
        otp_service=otp_service
    )

    assert factory.otp_management.otp_service is otp_service


def test_factory_returns_same_orchestrator_instance():
    cache = Mock(spec=CacheBaseAdaptor)
    otp_service = Mock(spec=OTPInterface)

    factory = AuthDependencyFactory(
        cache=cache,
        otp_service=otp_service
    )

    assert factory.get_auth_orchestrator() is factory.get_auth_orchestrator()
