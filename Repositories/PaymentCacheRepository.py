
import json
from typing import Any

from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor


class PaymentCacheRepository:

    PAYMENT_STATUS_TTL = 300

    def __init__(self, cache: RedisCacheAdaptor):
        self.cache = cache

    @staticmethod
    def _status_key(payment_id: str) -> str:
        return f"payment:status:{payment_id}"

    def get_payment_status(self, payment_id: str) -> dict[str, Any] | None:

        key = self._status_key(payment_id)

        cached_value = self.cache.get(key)

        if cached_value is None:
            return None

        try:
            return json.loads(cached_value)
        except json.JSONDecodeError:
            # Remove malformed cache entry.
            self.cache.delete(key)
            return None

    def set_payment_status(
        self,
        payment_id: str,
        payment_data: dict[str, Any],
    ) -> None:

        key = self._status_key(payment_id)

        value = json.dumps(payment_data)

        self.cache.set(
            key,
            value,
            self.PAYMENT_STATUS_TTL,
        )

    def invalidate_payment_status(self, payment_id: str) -> None:

        key = self._status_key(payment_id)

        self.cache.delete(key)
