import os
import re
import json
import hmac
import hashlib
import secrets

from dotenv import load_dotenv

load_dotenv()

class OTPManagement:

    def __init__(self, otp_service: object, cache: object):
        self.otp_service = otp_service
        self.cache = cache

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
            ttl=300,
        )
    
    def send_otp(self, mobile_number: str) -> bool:
        if not re.fullmatch(r"[6-9]\d{9}", mobile_number):
            raise ValueError("Invalid Indian mobile number")

        otp = self._generate_otp()
        otp_hash = self._hash_otp(mobile_number, otp)

        self._store_otp(mobile_number, otp_hash)

        try:
            self.otp_service.send_otp(mobile_number, otp)
        except Exception:
            self.cache.delete(self._get_otp_key(mobile_number))
            raise RuntimeError("Unable to send OTP. Please try again.")

        return True

    
    def verify_otp(self, mobile_number: str, otp: str) -> bool:
        # 1. Validate input format
        if not re.fullmatch(r"[6-9]\d{9}", mobile_number):
            raise ValueError("Invalid Indian mobile number")

        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP must contain exactly six digits")

        # 2. Retrieve OTP data from cache
        key = self._get_otp_key(mobile_number)
        stored_value = self.cache.get(key)

        if stored_value is None:
            return False  # OTP missing or expired

        try:
            otp_data = json.loads(stored_value)
            stored_hash = otp_data["otp_hash"]
            failed_attempts = int(otp_data["failed_attempts"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            self.cache.delete(key)
            raise RuntimeError("Invalid OTP data in cache") from exc

        # 3. Enforce maximum failed attempts
        max_attempts = 5

        if failed_attempts >= max_attempts:
            self.cache.delete(key)
            return False

        # 4. Hash the submitted OTP
        submitted_hash = self._hash_otp(mobile_number, otp)

        # 5. Compare hashes safely
        if not hmac.compare_digest(stored_hash, submitted_hash):
            failed_attempts += 1

            # Preserve the OTP's original expiry time
            remaining_ttl = self.cache.ttl(key)

            if remaining_ttl <= 0:
                self.cache.delete(key)
                return False

            otp_data["failed_attempts"] = failed_attempts

            self.cache.set(
                key,
                json.dumps(otp_data),
                ttl=remaining_ttl,
            )

            # Invalidate immediately after the fifth failure
            if failed_attempts >= max_attempts:
                self.cache.delete(key)

            return False

        # 6. Correct OTP: consume it so it cannot be reused
        self.cache.delete(key)
        return True

