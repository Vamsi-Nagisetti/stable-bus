
import hashlib
import logging
import math

from Adaptors.Cache.CacheBaseAdaptor import CacheBaseAdaptor


logger = logging.getLogger("stablebus.management.rate_limit")


class RateLimitExceededError(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimitManagement:

    WINDOW_SECONDS = 600
    COOLDOWN_SECONDS = 30

    MOBILE_LIMIT = 3
    IP_LIMIT = 10

    RATE_LIMIT_SCRIPT = """
    local mobile_count = tonumber(redis.call('GET', KEYS[1]) or '0')
    local ip_count = tonumber(redis.call('GET', KEYS[2]) or '0')
    local cooldown_ttl = redis.call('TTL', KEYS[3])

    if cooldown_ttl > 0 then
        return {-2, cooldown_ttl}
    end

    if mobile_count >= tonumber(ARGV[1]) then
        return {0, redis.call('TTL', KEYS[1])}
    end

    if ip_count >= tonumber(ARGV[2]) then
        return {-1, redis.call('TTL', KEYS[2])}
    end

    mobile_count = redis.call('INCR', KEYS[1])
    if mobile_count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[3])
    end

    ip_count = redis.call('INCR', KEYS[2])
    if ip_count == 1 then
        redis.call('EXPIRE', KEYS[2], ARGV[3])
    end

    redis.call('SET', KEYS[3], '1', 'EX', ARGV[4])

    return {1, 0}
    """

    def __init__(self, cache: CacheBaseAdaptor):
        self.cache = cache

    @staticmethod
    def _hash_identifier(identifier: str) -> str:
        return hashlib.sha256(
            identifier.encode("utf-8")
        ).hexdigest()

    def check_otp_request(
        self,
        mobile_number: str,
        client_ip: str
    ) -> None:

        mobile_hash = self._hash_identifier(mobile_number)
        ip_hash = self._hash_identifier(client_ip)

        mobile_key = f"stablebus:ratelimit:otp:mobile:{mobile_hash}"
        ip_key = f"stablebus:ratelimit:otp:ip:{ip_hash}"
        cooldown_key = f"stablebus:ratelimit:otp:cooldown:{mobile_hash}"

        result = self.cache.execute_atomic(
            script=self.RATE_LIMIT_SCRIPT,
            keys=[mobile_key, ip_key, cooldown_key],
            args=[
                self.MOBILE_LIMIT,
                self.IP_LIMIT,
                self.WINDOW_SECONDS,
                self.COOLDOWN_SECONDS
            ]
        )

        status_code = int(result[0])
        retry_after = int(result[1])

        if status_code == 1:
            logger.info("OTP request permitted")
            return

        if status_code == -2:
            message = "Please wait before requesting another OTP."
        elif status_code == 0:
            message = "OTP request limit exceeded for this mobile number."
        elif status_code == -1:
            message = "OTP request limit exceeded for this IP address."
        else:
            logger.error("Unexpected rate limiter response")
            raise RuntimeError("Unable to process OTP request")

        retry_after = max(1, retry_after)

        logger.warning(
            "OTP request rejected | reason=%s | retry_after=%s",
            status_code,
            retry_after
        )

        raise RateLimitExceededError(
            message=message,
            retry_after=retry_after
        )


    def clear_otp_cooldown(self, mobile_number: str) -> None:
        mobile_hash = self._hash_identifier(mobile_number)

        cooldown_key = (
            f"stablebus:ratelimit:otp:cooldown:{mobile_hash}"
        )

        self.cache.delete(cooldown_key)

        logger.info("OTP resend cooldown cleared after delivery failure")
