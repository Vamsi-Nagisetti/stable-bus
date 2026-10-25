
from abc import ABC, abstractmethod
from typing import Optional


class CacheBaseAdaptor(ABC):

    @abstractmethod
    def set(self, key: str, value: str, ttl: int) -> None:
        pass

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass

    @abstractmethod
    def ttl(self, key: str) -> int:
        pass
