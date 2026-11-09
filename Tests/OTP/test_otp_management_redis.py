
import json
import uuid
import pytest

from Management.OtpMangement import OTPManagement
from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor
from concurrent.futures import ThreadPoolExecutor

@pytest.fixture
def otp_management():
    redis_adaptee = RedisCacheAdaptee()
    cache = RedisCacheAdaptor(redis_adaptee)

    class MockOTPService:
        def send_otp(self, mobile_number, otp):
            pass

    management = OTPManagement(
        otp_service=MockOTPService(),
        cache=cache
    )

    yield management

    redis_adaptee.close()


@pytest.fixture
def test_mobile():
    # Unique test number prevents collisions with other test runs.
    return "9" + str(uuid.uuid4().int)[:9]


def store_test_otp(otp_management, mobile, otp="123456"):
    key = otp_management._get_otp_key(mobile)
    otp_hash = otp_management._hash_otp(mobile, otp)

    value = json.dumps({
        "otp_hash": otp_hash,
        "failed_attempts": 0
    })

    otp_management.cache.set(key, value, ttl=60)
    return key

def test_correct_otp_is_verified_and_deleted(otp_management, test_mobile):
    key = store_test_otp(otp_management, test_mobile)

    assert otp_management.verify_otp(test_mobile, "123456") is True
    assert otp_management.cache.get(key) is None


def test_incorrect_otp_increments_attempts(otp_management, test_mobile):
    key = store_test_otp(otp_management, test_mobile)

    assert otp_management.verify_otp(test_mobile, "654321") is False

    stored_data = json.loads(otp_management.cache.get(key))
    assert stored_data["failed_attempts"] == 1


def test_fifth_failed_attempt_deletes_otp(otp_management, test_mobile):
    key = store_test_otp(otp_management, test_mobile)

    for _ in range(5):
        assert otp_management.verify_otp(test_mobile, "654321") is False

    assert otp_management.cache.get(key) is None


def test_expired_otp_is_rejected(otp_management, test_mobile):
    key = otp_management._get_otp_key(test_mobile)

    otp_management.cache.set(
        key,
        json.dumps({
            "otp_hash": otp_management._hash_otp(test_mobile, "123456"),
            "failed_attempts": 0
        }),
        ttl=1
    )

    import time
    time.sleep(2)

    assert otp_management.verify_otp(test_mobile, "123456") is False
    assert otp_management.cache.get(key) is None


def test_otp_cannot_be_reused(otp_management, test_mobile):
    store_test_otp(otp_management, test_mobile)

    assert otp_management.verify_otp(test_mobile, "123456") is True
    assert otp_management.verify_otp(test_mobile, "123456") is False

def test_concurrent_otp_verification_only_one_succeeds(
    otp_management, test_mobile
):
    store_test_otp(otp_management, test_mobile)

    def verify():
        return otp_management.verify_otp(test_mobile, "123456")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: verify(), range(2)))

    # Exactly one request must successfully consume the OTP.
    assert results.count(True) == 1
    assert results.count(False) == 1