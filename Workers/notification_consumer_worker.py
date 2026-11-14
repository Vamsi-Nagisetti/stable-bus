
import logging
import os
import time

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

EVENT_TYPE = "BOOKING_CONFIRMED"


def process_message(message, consumer, handler):
    event = message.value
    event_type = event.get("event_type")

    if event_type != EVENT_TYPE:
        logger.warning(
            "Ignoring unsupported event type: %s",
            event_type,
        )
        consumer.commit()
        return

    while True:
        try:
            handler(event)
            consumer.commit()
            return

        except Exception:
            logger.exception(
                "Notification processing failed. Retrying event."
            )
            time.sleep(5)


def main():
    load_dotenv()

    transport = os.getenv(
        "EVENT_TRANSPORT",
        "direct",
    ).strip().lower()

    if transport != "kafka":
        raise RuntimeError(
            "Kafka notification consumer cannot run when "
            f"EVENT_TRANSPORT='{transport}'. "
            "Set EVENT_TRANSPORT=kafka to enable it."
        )

    # Kafka imports happen only after validating the transport.
    from messageQueues.KafkaEventConsumer import KafkaEventConsumer
    from Adaptors.Notifications.ResendEmailAdapter import ResendEmailAdapter
    from Services.Notifications.NotificationService import NotificationService
    from Services.Notifications.BookingConfirmationHandler import (
        BookingConfirmationHandler,
    )

    consumer = None
    notification_service = None

    try:
        consumer = KafkaEventConsumer()

        notification_provider = ResendEmailAdapter()
        notification_service = NotificationService(
            notification_provider
        )

        handler = BookingConfirmationHandler(
            notification_service
        )

        logger.info(
            "Kafka notification consumer started"
        )

        while True:
            message = consumer.consume(timeout=10.0)

            if message is None:
                continue

            process_message(
                message=message,
                consumer=consumer,
                handler=handler,
            )

    except KeyboardInterrupt:
        logger.info(
            "Kafka notification consumer stopping..."
        )

    finally:
        if consumer is not None:
            consumer.close()

        if notification_service is not None:
            notification_service.close()

        logger.info(
            "Kafka notification consumer stopped"
        )


if __name__ == "__main__":
    main()
