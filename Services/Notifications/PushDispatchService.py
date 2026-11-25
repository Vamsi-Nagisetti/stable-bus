"""Shared push-sending logic (Expo).

Used by the booking-confirmation handler, the wallet notifications and the
admin "send custom notification" endpoint. It:
  * chunks messages into batches of <= 100 (Expo limit)
  * reads per-message tickets and deactivates tokens Expo reports as
    DeviceNotRegistered, so we stop pushing to dead devices
"""
import logging
from typing import Any, Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models.PushDevice import PushDevice
from Services.Notifications.ExpoPushService import ExpoPushService

logger = logging.getLogger("stablebus.notifications.dispatch")

EXPO_BATCH_SIZE = 100
PERMANENT_ERRORS = {
    "DeviceNotRegistered",
    "InvalidCredentials",
    "MessageTooBig",
    "MismatchSenderId",
}


class PushDispatchResult:
    def __init__(self):
        self.attempted = 0
        self.accepted = 0
        self.failed = 0
        self.deactivated = 0
        self.transient_failures = 0  # network / 5xx: worth retrying
        self.errors: list[str] = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "accepted": self.accepted,
            "failed": self.failed,
            "deactivated_devices": self.deactivated,
            "transient_failures": self.transient_failures,
            "errors": self.errors[:20],
        }


class PushDispatchService:
    def __init__(self, push_service: ExpoPushService | None = None):
        self.push_service = push_service or ExpoPushService()

    # ------------------------------------------------------------------
    # Device lookup
    # ------------------------------------------------------------------
    @staticmethod
    def tokens_for_users(
        db: Session,
        user_ids: Iterable[str],
        platform: str | None = None,
    ) -> list[str]:
        ids = [str(u) for u in user_ids]
        if not ids:
            return []
        stmt = select(PushDevice.expo_push_token).where(
            PushDevice.user_id.in_(ids),
            PushDevice.is_active.is_(True),
        )
        if platform:
            stmt = stmt.where(PushDevice.platform == platform)
        return list(dict.fromkeys(db.execute(stmt).scalars().all()))

    @staticmethod
    def all_active_tokens(
        db: Session, platform: str | None = None
    ) -> list[str]:
        stmt = select(PushDevice.expo_push_token).where(
            PushDevice.is_active.is_(True)
        )
        if platform:
            stmt = stmt.where(PushDevice.platform == platform)
        return list(dict.fromkeys(db.execute(stmt).scalars().all()))

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def send_to_tokens(
        self,
        db: Session,
        tokens: list[str],
        title: str,
        body: str,
        data: dict | None = None,
    ) -> PushDispatchResult:
        result = PushDispatchResult()
        tokens = list(dict.fromkeys(tokens))

        for start in range(0, len(tokens), EXPO_BATCH_SIZE):
            chunk = tokens[start:start + EXPO_BATCH_SIZE]
            messages = [
                {
                    "to": token,
                    "sound": "default",
                    "title": title,
                    "body": body,
                    "data": data or {},
                    "channelId": "default",
                    "priority": "high",
                }
                for token in chunk
            ]
            result.attempted += len(chunk)

            try:
                tickets = self.push_service.send(messages)
            except Exception as exc:  # network / Expo outage
                logger.exception("Expo push request failed")
                result.failed += len(chunk)
                result.transient_failures += len(chunk)
                result.errors.append(str(exc)[:300])
                continue

            dead_tokens: list[str] = []
            for token, ticket in zip(chunk, tickets):
                if ticket.get("status") == "ok":
                    result.accepted += 1
                    continue

                result.failed += 1
                error = (ticket.get("details") or {}).get("error")
                result.errors.append(
                    f"{error or ticket.get('message', 'unknown')}"
                )
                if error in PERMANENT_ERRORS and error == "DeviceNotRegistered":
                    dead_tokens.append(token)

            # Expo returns one ticket per message; if it returned fewer,
            # the remainder is unknown -> count as transient.
            missing = len(chunk) - len(tickets)
            if missing > 0:
                result.failed += missing
                result.transient_failures += missing

            if dead_tokens:
                db.execute(
                    update(PushDevice)
                    .where(PushDevice.expo_push_token.in_(dead_tokens))
                    .values(is_active=False)
                )
                db.commit()
                result.deactivated += len(dead_tokens)
                logger.info(
                    "Deactivated %s unregistered push devices",
                    len(dead_tokens),
                )

        return result
