
import logging
from typing import Any, Callable

from messageQueues.BaseProducer import BaseProducer

logger = logging.getLogger(__name__)


EventHandler = Callable[[dict[str, Any]], None]


class DirectEventDispatcher(BaseProducer):
    """
    Dispatch outbox events directly to registered Python handlers.

    This implementation does not initialize Kafka or perform
    any network-based message transport.
    """

    def __init__(
        self,
        handlers: dict[str, EventHandler] | None = None,
    ):
        self.handlers = handlers or {}
        self.topic = "direct"

    def register_handler(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        if not event_type or not event_type.strip():
            raise ValueError("Event type is required")

        if not callable(handler):
            raise TypeError("Event handler must be callable")

        if event_type in self.handlers:
            raise ValueError(
                f"Handler already registered for {event_type}"
            )

        self.handlers[event_type] = handler

        logger.info(
            "Registered direct event handler: %s",
            event_type,
        )

    def publish(
        self,
        topic: str,
        key: str,
        event: dict[str, Any],
    ) -> None:
        event_type = event.get("event_type")

        if not event_type:
            raise ValueError("Event is missing event_type")

        handler = self.handlers.get(event_type)

        if handler is None:
            raise RuntimeError(
                f"No direct handler registered for event: {event_type}"
            )

        logger.info(
            "Dispatching event directly: event_type=%s key=%s",
            event_type,
            key,
        )

        handler(event)

    def close(self) -> None:
        logger.info("Direct event dispatcher closed")
