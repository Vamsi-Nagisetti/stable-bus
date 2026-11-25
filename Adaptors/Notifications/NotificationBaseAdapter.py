from abc import ABC, abstractmethod
from typing import Any


class NotificationBaseAdapter(ABC):

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def close(self) -> None:
        pass