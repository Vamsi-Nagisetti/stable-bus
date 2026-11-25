import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.database import SessionLocal
from models.NotificationDelivery import NotificationDelivery
from models.PushDevice import PushDevice
from Services.Notifications.ExpoPushService import ExpoPushService

logger = logging.getLogger("stablebus.notifications.push")

EVENT_TYPE = "BOOKING_CONFIRMED"
CHANNEL = "PUSH"


class PushBookingConfirmationHandler:
    def __init__(self, push_service=None, session_factory=SessionLocal):
        self.push_service = push_service or ExpoPushService()
        self.session_factory = session_factory

    def __call__(self, event: dict) -> None:
        event_id = event.get("event_id")
        if not event_id:
            raise ValueError("Push event is missing event_id")
        if event.get("event_type") != EVENT_TYPE:
            return

        payload = event.get("payload") or {}
        user_id = payload.get("user_id")
        if not user_id:
            logger.info("Skipping push for guest booking event_id=%s", event_id)
            return

        with self.session_factory() as db:
            existing = db.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.event_id == event_id,
                    NotificationDelivery.channel == CHANNEL,
                )
            ).scalar_one_or_none()

            if existing and existing.status == "SENT":
                return
            if existing is None:
                existing = NotificationDelivery(
                    event_id=event_id,
                    channel=CHANNEL,
                    status="PENDING",
                    attempts=0,
                )
                db.add(existing)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    existing = db.execute(
                        select(NotificationDelivery).where(
                            NotificationDelivery.event_id == event_id,
                            NotificationDelivery.channel == CHANNEL,
                        )
                    ).scalar_one()

            devices = db.execute(
                select(PushDevice).where(
                    PushDevice.user_id == str(user_id),
                    PushDevice.is_active.is_(True),
                )
            ).scalars().all()
            tokens = [device.expo_push_token for device in devices]

            if not tokens:
                existing.status = "FAILED"
                existing.last_error = "No active push devices registered"
                existing.attempts += 1
                db.commit()
                logger.info("No active push devices for user_id=%s", user_id)
                return

            booking_id = payload.get("booking_id", "")
            journey_date = payload.get("journey_date") or ""
            messages = [
                {
                    "to": token,
                    "sound": "default",
                    "title": "StableBus booking confirmed!",
                    "body": f"Your bus booking is confirmed. Journey date: {journey_date}".strip(),
                    "data": {
                        "type": "BOOKING_CONFIRMED",
                        "booking_id": str(booking_id),
                    },
                    "channelId": "default",
                    "priority": "high",
                }
                for token in tokens
            ]

            try:
                receipts = self.push_service.send(messages)
                errors = [
                    receipt for receipt in receipts
                    if receipt.get("status") == "error"
                ]
                if errors:
                    raise RuntimeError(f"Expo rejected push messages: {errors}")

                existing.status = "SENT"
                existing.sent_at = datetime.now(timezone.utc)
                existing.last_error = None
                existing.attempts += 1
                db.commit()
                logger.info(
                    "Booking push sent event_id=%s device_count=%s",
                    event_id, len(tokens),
                )
            except Exception as exc:
                existing.status = "PENDING"
                existing.attempts += 1
                existing.last_error = str(exc)[:2000]
                db.commit()
                logger.exception("Push delivery failed event_id=%s", event_id)
                raise
