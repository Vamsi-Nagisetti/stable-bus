import logging
import os
from typing import Any

import requests

logger = logging.getLogger("stablebus.notifications.expo")


class ExpoPushService:
    """Small server-side client for Expo's Push API."""

    PUSH_URL = "https://exp.host/--/api/v2/push/send"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.access_token = os.getenv("EXPO_ACCESS_TOKEN")

    def send(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not messages:
            return []

        headers = {
            "Accept": "application/json",
            "Accept-encoding": "gzip, deflate",
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        response = requests.post(
            self.PUSH_URL,
            json=messages,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()

        if body.get("errors"):
            raise RuntimeError(f"Expo push API returned errors: {body['errors']}")

        data = body.get("data", [])
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise RuntimeError("Unexpected response from Expo Push API")

        return data
