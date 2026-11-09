
from abc import ABC, abstractmethod
from typing import Any


class BaseProducer(ABC):

    @abstractmethod
    def publish(
        self,
        topic: str,
        key: str,
        event: dict[str, Any],
    ) -> None:
        """Publish an event to a messaging topic."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release producer resources."""
        raise NotImplementedError
