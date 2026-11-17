
from abc import ABC, abstractmethod
from typing import Any


class BaseConsumer(ABC):

    @abstractmethod
    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to one or more topics."""
        raise NotImplementedError

    @abstractmethod
    def consume(self, timeout: float = 1.0) -> Any | None:
        """Retrieve the next event, if available."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release consumer resources."""
        raise NotImplementedError
