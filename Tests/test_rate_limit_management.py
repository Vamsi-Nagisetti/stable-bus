
from unittest.mock import Mock

import pytest

from Management.RateLimitManagement import (
    RateLimitManagement,
    RateLimitExceededError
)


@pytest.fixture
def cache():
    return Mock()


@pytest.fixture
def rate_limiter(cache):
    return RateLimitManagement(cache)


def test_first_otp_request_is_allowed(rate_limiter, cache):
    cache.execute_atomic.return_value = [1, 0]

    result = rate_limiter.check_otp_request(
        "9876543210",
        "127.0.0.1"
    )

    assert result is None
    cache.execute_atomic.assert_called_once()


def test_cooldown_rejects_request(rate_limiter, cache):
    cache.execute_atomic.return_value = [-2, 20]

    with pytest.raises(RateLimitExceededError) as exc:
        rate_limiter.check_otp_request(
            "9876543210",
            "127.0.0.1"
        )

    assert exc.value.retry_after == 20


def test_mobile_limit_rejects_request(rate_limiter, cache):
    cache.execute_atomic.return_value = [0, 300]

    with pytest.raises(RateLimitExceededError) as exc:
        rate_limiter.check_otp_request(
            "9876543210",
            "127.0.0.1"
        )

    assert exc.value.retry_after == 300


def test_ip_limit_rejects_request(rate_limiter, cache):
    cache.execute_atomic.return_value = [-1, 250]

    with pytest.raises(RateLimitExceededError) as exc:
        rate_limiter.check_otp_request(
            "9876543210",
            "127.0.0.1"
        )

    assert exc.value.retry_after == 250


def test_invalid_retry_after_uses_minimum(
    rate_limiter,
    cache
):
    cache.execute_atomic.return_value = [-2, -1]

    with pytest.raises(RateLimitExceededError) as exc:
        rate_limiter.check_otp_request(
            "9876543210",
            "127.0.0.1"
        )

    assert exc.value.retry_after == 1


def test_mobile_number_is_not_exposed_in_redis_keys(
    rate_limiter,
    cache
):
    cache.execute_atomic.return_value = [1, 0]

    rate_limiter.check_otp_request(
        "9876543210",
        "127.0.0.1"
    )

    keys = cache.execute_atomic.call_args.kwargs["keys"]

    assert "9876543210" not in str(keys)


def test_clear_otp_cooldown_deletes_only_cooldown(
    rate_limiter,
    cache
):
    mobile = "9876543210"

    rate_limiter.clear_otp_cooldown(mobile)

    mobile_hash = rate_limiter._hash_identifier(mobile)

    cooldown_key = (
        f"stablebus:ratelimit:otp:cooldown:{mobile_hash}"
    )

    cache.delete.assert_called_once_with(cooldown_key)
