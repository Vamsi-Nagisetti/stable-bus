import os
import requests
from dotenv import load_dotenv
from typing import Any

from Adaptors.Notifications.NotificationBaseAdapter import (
    NotificationBaseAdapter,
)

load_dotenv()


class ResendEmailAdapter(NotificationBaseAdapter):

    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("RESEND_FROM_EMAIL")

        if not self.api_key:
            raise RuntimeError("RESEND_API_KEY is missing")

        if not self.from_email:
            raise RuntimeError("RESEND_FROM_EMAIL is missing")

        self.url = "https://api.resend.com/emails"

    def send_email(
        self,
        to_email: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> dict[str, Any]:

        if not to_email or "@" not in to_email:
            raise ValueError("Invalid recipient email")

        if not subject.strip():
            raise ValueError("Email subject cannot be empty")

        if not html and not text:
            raise ValueError("Email must contain HTML or text")

        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": subject,
        }

        if html:
            payload["html"] = html

        if text:
            payload["text"] = text

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=15,
            )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as exc:
            raise RuntimeError(
                "Failed to send email through Resend"
            ) from exc

    def close(self) -> None:
        pass