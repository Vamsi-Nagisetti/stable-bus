import os
import re
import json
import hmac
import hashlib
import secrets

from dotenv import load_dotenv

load_dotenv()

class OTPDeliveryError(Exception):
    """Raised when the OTP delivery provider fails."""
    pass

class OTPManagement:

    def __init__(self, otp_service: object, cache: object):
        self.otp_service = otp_service
        self.cache = cache
        self.VERIFY_OTP_SCRIPT = """
            local key = KEYS[1]
            local submitted_hash = ARGV[1]
            local max_attempts = tonumber(ARGV[2])

            -- Read OTP data
            local stored_value = redis.call('GET', key)

            if not stored_value then
                return {-1, 0}
            end

            -- Decode stored JSON
            local ok, otp_data = pcall(cjson.decode, stored_value)

            if not ok or not otp_data.otp_hash or otp_data.failed_attempts == nil then
                redis.call('DEL', key)
                return {-2, 0}
            end

            local stored_hash = otp_data.otp_hash
            local failed_attempts = tonumber(otp_data.failed_attempts)

            if not failed_attempts then
                redis.call('DEL', key)
                return {-2, 0}
            end

            -- Check maximum attempts
            if failed_attempts >= max_attempts then
                redis.call('DEL', key)
                return {0, failed_attempts}
            end

            -- Constant-time hash comparison
            local function constant_time_equals(a, b)
                local diff = (#a == #b) and 0 or 1
                local max_length = math.max(#a, #b)

                for i = 1, max_length do
                    local x = string.byte(a, i) or 0
                    local y = string.byte(b, i) or 0
                    diff = diff + (x ~= y and 1 or 0)
                end

                return diff == 0
            end

            -- Correct OTP
            if constant_time_equals(stored_hash, submitted_hash) then
                redis.call('DEL', key)
                return {1, failed_attempts}
            end

            -- Incorrect OTP: increment attempts
            failed_attempts = failed_attempts + 1

            -- Fifth failure: invalidate OTP
            if failed_attempts >= max_attempts then
                redis.call('DEL', key)
                return {0, failed_attempts}
            end

            -- Preserve original expiry
            local remaining_ttl = redis.call('PTTL', key)

            if remaining_ttl <= 0 then
                redis.call('DEL', key)
                return {-1, failed_attempts}
            end

            otp_data.failed_attempts = failed_attempts

            redis.call(
                'SET',
                key,
                cjson.encode(otp_data),
                'PX',
                remaining_ttl
            )

            return {0, failed_attempts}
            """

    def _generate_otp(self) -> str:
        return f"{secrets.randbelow(900000) + 100000}"

    def _get_otp_key(self, mobile_number: str) -> str:
        return f"stablebus:otp:{mobile_number}"


    def _hash_otp(self, mobile_number: str, otp: str) -> str:
        secret = os.getenv("OTP_HMAC_SECRET")

        if not secret:
            raise RuntimeError("OTP_HMAC_SECRET is missing")

        message = f"{mobile_number}:{otp}".encode("utf-8")

        return hmac.new(
            secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    def _store_otp(self, mobile_number: str, otp_hash: str) -> None:
        key = self._get_otp_key(mobile_number)

        otp_data = {
            "otp_hash": otp_hash,
            "failed_attempts": 0,
        }

        self.cache.set(
            key,
            json.dumps(otp_data),
            ttl=60,
        )
    
    def send_otp(self, mobile_number: str) -> bool:
        if not re.fullmatch(r"[6-9]\d{9}", mobile_number):
            raise ValueError("Invalid Indian mobile number")

        otp = self._generate_otp()
        otp_hash = self._hash_otp(mobile_number, otp)

        self._store_otp(mobile_number, otp_hash)

        try:
            self.otp_service.send_otp(mobile_number, otp)

        except Exception as exc:
            self.cache.delete(self._get_otp_key(mobile_number))

            raise OTPDeliveryError(
                "Unable to send OTP. Please try again."
            ) from exc
        return True

    
    def verify_otp(self, mobile_number: str, otp: str) -> bool:

        if not re.fullmatch(r"[6-9]\d{9}", mobile_number):
            raise ValueError("Invalid Indian mobile number")

        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP must contain exactly six digits")

        key = self._get_otp_key(mobile_number)

        submitted_hash = self._hash_otp(mobile_number, otp)

        result = self.cache.execute_atomic(
            script=self.VERIFY_OTP_SCRIPT,
            keys=[key],
            args=[submitted_hash, 5],
        )

        status_code = int(result[0])

        if status_code == 1:
            return True

        if status_code == 0:
            return False

        if status_code == -1:
            return False

        if status_code == -2:
            raise RuntimeError("Invalid OTP data in cache")

        raise RuntimeError("Unexpected OTP verification response")
