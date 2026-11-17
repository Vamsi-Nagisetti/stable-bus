from typing import Any

from Adaptors.Notifications.NotificationBaseAdapter import (
    NotificationBaseAdapter,
)


class NotificationService:

    def __init__(
        self,
        notification_provider: NotificationBaseAdapter,
    ):
        self.notification_provider = notification_provider

    def send_email(
        self,
        to_email: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> dict[str, Any]:

        return self.notification_provider.send_email(
            to_email=to_email,
            subject=subject,
            html=html,
            text=text,
        )

    def close(self) -> None:
        self.notification_provider.close()