
from abc import ABC, abstractmethod
from typing import Optional, Any


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

    @abstractmethod
    def execute_atomic(
        self,
        script: str,
        keys: list[str],
        args: list[Any]
    ) -> Any:
        """
        Execute a Redis Lua script atomically.

        Args:
            script: Lua script to execute.
            keys: Redis keys accessed by the script.
            args: Arguments passed to the script.

        Returns:
            Result returned by the Lua script.
        """
        pass
