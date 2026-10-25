
from typing import Optional

from Adaptors.Cache.CacheBaseAdaptor import CacheBaseAdaptor
from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee


class RedisCacheAdaptor(CacheBaseAdaptor):

    def __init__(self, adaptee: RedisCacheAdaptee):
        self.adaptee = adaptee

    def set(self, key: str, value: str, ttl: int) -> None:
        self.adaptee.set_value(key, value, ttl)

    def get(self, key: str) -> Optional[str]:
        return self.adaptee.get_value(key)

    def delete(self, key: str) -> None:
        self.adaptee.delete_value(key)

    def ttl(self, key: str) -> int:
        return self.adaptee.get_ttl(key)
