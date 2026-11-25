import logging

logger = logging.getLogger("stablebus.notifications.composite")


class BookingNotificationHandler:
    """Runs the existing email delivery and the push channel.

    The channels are isolated: a failure in one never prevents the other
    from running. Each channel tracks its own delivery state
    (NotificationDelivery.channel), so re-running the event after a
    transient failure never re-sends a channel that already succeeded.
    """

    def __init__(self, email_handler, push_handler):
        self.email_handler = email_handler
        self.push_handler = push_handler

    def __call__(self, event: dict) -> None:
        first_error = None

        for name, handler in (
            ("email", self.email_handler),
            ("push", self.push_handler),
        ):
            try:
                handler(event)
            except Exception as exc:
                logger.exception(
                    "Notification channel failed channel=%s event_id=%s",
                    name,
                    event.get("event_id"),
                )
                if first_error is None:
                    first_error = exc

        # Re-raise so the outbox retries the event with backoff.
        if first_error is not None:
            raise first_error
