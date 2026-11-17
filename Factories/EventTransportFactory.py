
import logging
import os

from dotenv import load_dotenv

from messageQueues.DirectEventDispatcher import DirectEventDispatcher

logger = logging.getLogger(__name__)

load_dotenv()

EVENT_TYPE = "BOOKING_CONFIRMED"


def create_event_transport():
    """
    Create the configured event transport.

    Returns:
        tuple:
            producer: Event producer/dispatcher.
            resources: Additional resources that must be closed.
    """

    transport = os.getenv("EVENT_TRANSPORT", "direct").strip().lower()

    if transport == "direct":
        from Adaptors.Notifications.ResendEmailAdapter import (
            ResendEmailAdapter,
        )
        from Services.Notifications.NotificationService import (
            NotificationService,
        )
        from Services.Notifications.BookingConfirmationHandler import (
            BookingConfirmationHandler,
        )

        notification_provider = ResendEmailAdapter()
        notification_service = NotificationService(
            notification_provider
        )

        handler = BookingConfirmationHandler(
            notification_service
        )

        dispatcher = DirectEventDispatcher()

        dispatcher.register_handler(
            EVENT_TYPE,
            handler,
        )

        logger.info(
            "Event transport initialized: DIRECT"
        )

        return dispatcher, [notification_service]

    if transport == "kafka":
        # Import Kafka only when Kafka transport is selected.
        from messageQueues.KafkaEventProducer import (
            KafkaEventProducer,
        )

        producer = KafkaEventProducer()

        logger.info(
            "Event transport initialized: KAFKA"
        )

        return producer, []

    raise ValueError(
        f"Unsupported EVENT_TRANSPORT='{transport}'. "
        "Supported values: direct, kafka"
    )
