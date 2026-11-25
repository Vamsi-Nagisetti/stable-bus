    import logging

    logger = logging.getLogger("stablebus.notifications.composite")


    class BookingNotificationHandler:
        """Runs existing email delivery and the additional push channel."""

        def __init__(self, email_handler, push_handler):
            self.email_handler = email_handler
            self.push_handler = push_handler

        def __call__(self, event: dict) -> None:
            # Keep email behavior intact. Each channel tracks its own delivery state.
            self.email_handler(event)
            self.push_handler(event)
