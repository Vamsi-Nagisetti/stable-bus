
import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

from Adaptors.Notifications.NotificationBaseAdapter import (
    NotificationBaseAdapter,
)

load_dotenv()

logger = logging.getLogger(__name__)


class ResendEmailAdapter(NotificationBaseAdapter):

    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("RESEND_FROM_EMAIL")

        if not self.api_key:
            logger.error("Resend initialization failed: RESEND_API_KEY is missing")
            raise RuntimeError("RESEND_API_KEY is missing")

        if not self.from_email:
            logger.error("Resend initialization failed: RESEND_FROM_EMAIL is missing")
            raise RuntimeError("RESEND_FROM_EMAIL is missing")

        self.url = "https://api.resend.com/emails"

        logger.info(
            "ResendEmailAdapter initialized successfully. sender=%s",
            self.from_email,
        )

    def send_email(
        self,
        to_email: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> dict[str, Any]:

        # Validate request
        if not to_email or "@" not in to_email:
            logger.error(
                "Email validation failed: invalid recipient=%s",
                to_email,
            )
            raise ValueError("Invalid recipient email")

        if not subject or not subject.strip():
            logger.error(
                "Email validation failed: empty subject. recipient=%s",
                to_email,
            )
            raise ValueError("Email subject cannot be empty")

        if not html and not text:
            logger.error(
                "Email validation failed: missing email content. recipient=%s",
                to_email,
            )
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

        logger.info(
            "Sending email through Resend. recipient=%s subject=%s",
            to_email,
            subject,
        )

        try:
            response = requests.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=15,
            )

            response.raise_for_status()

            try:
                result = response.json()
            except ValueError:
                result = {}

            logger.info(
                "Email sent successfully through Resend. "
                "recipient=%s resend_email_id=%s status_code=%s",
                to_email,
                result.get("id"),
                response.status_code,
            )

            return result

        except requests.HTTPError as exc:
            response = exc.response

            status_code = (
                response.status_code if response is not None else None
            )

            # Resend returns useful validation details in its response body.
            error_response = (
                response.text[:2000] if response is not None else str(exc)
            )

            logger.error(
                "Resend rejected email request. "
                "recipient=%s status_code=%s response=%s",
                to_email,
                status_code,
                error_response,
            )

            raise RuntimeError(
                f"Resend rejected email request (HTTP {status_code}): "
                f"{error_response}"
            ) from exc

        except requests.Timeout as exc:
            logger.error(
                "Resend email request timed out. recipient=%s timeout=15s",
                to_email,
                exc_info=True,
            )
            raise RuntimeError(
                "Resend email request timed out"
            ) from exc

        except requests.ConnectionError as exc:
            logger.error(
                "Could not connect to Resend. recipient=%s",
                to_email,
                exc_info=True,
            )
            raise RuntimeError(
                "Could not connect to Resend"
            ) from exc

        except requests.RequestException as exc:
            logger.exception(
                "Unexpected Resend request failure. recipient=%s",
                to_email,
            )
            raise RuntimeError(
                "Failed to send email through Resend"
            ) from exc

    def close(self) -> None:
        logger.info("ResendEmailAdapter closed")
