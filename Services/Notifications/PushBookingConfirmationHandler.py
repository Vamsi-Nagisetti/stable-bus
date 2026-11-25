import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.database import SessionLocal
from models.NotificationDelivery import NotificationDelivery
from Services.Notifications.PushDispatchService import PushDispatchService

logger = logging.getLogger("stablebus.notifications.push")

EVENT_TYPE = "BOOKING_CONFIRMED"
CHANNEL = "PUSH"
MAX_ATTEMPTS = 5


class PushBookingConfirmationHandler:
    """Sends the 'booking confirmed' push to every active device of the user.

    * Idempotent per event (NotificationDelivery event_id + channel=PUSH).
    * Permanent failures (no devices, dead tokens) are final - no endless
      outbox retries.
    * Transient failures (Expo / network down) are retried up to
      MAX_ATTEMPTS, then marked FAILED.
    """

    def __init__(self, push_service=None, session_factory=SessionLocal):
        self.dispatcher = PushDispatchService(push_service)
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
            delivery = db.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.event_id == event_id,
                    NotificationDelivery.channel == CHANNEL,
                )
            ).scalar_one_or_none()

            if delivery is None:
                delivery = NotificationDelivery(
                    event_id=event_id,
                    channel=CHANNEL,
                    status="PENDING",
                    attempts=0,
                )
                db.add(delivery)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    delivery = db.execute(
                        select(NotificationDelivery).where(
                            NotificationDelivery.event_id == event_id,
                            NotificationDelivery.channel == CHANNEL,
                        )
                    ).scalar_one()

            if delivery.status in ("SENT", "FAILED"):
                return

            tokens = self.dispatcher.tokens_for_users(db, [user_id])
            if not tokens:
                delivery.status = "FAILED"
                delivery.last_error = "No active push devices registered"
                delivery.attempts += 1
                db.commit()
                logger.info("No active push devices for user_id=%s", user_id)
                return

            booking_id = str(payload.get("booking_id", ""))
            journey_date = payload.get("journey_date") or ""
            operator = payload.get("operator_name") or ""
            body = "Your bus booking is confirmed."
            if journey_date:
                body += f" Journey date: {journey_date}."
            if operator:
                body += f" Operator: {operator}."

            result = self.dispatcher.send_to_tokens(
                db,
                tokens,
                title="StableBus booking confirmed!",
                body=body,
                data={
                    "type": "BOOKING_CONFIRMED",
                    "booking_id": booking_id,
                },
            )

            delivery.attempts += 1

            if result.accepted > 0:
                delivery.status = "SENT"
                delivery.sent_at = datetime.now(timezone.utc)
                delivery.last_error = None
                db.commit()
                logger.info(
                    "Booking push sent event_id=%s result=%s",
                    event_id, result.as_dict(),
                )
                return

            delivery.last_error = "; ".join(result.errors)[:2000] or None

            if result.transient_failures and delivery.attempts < MAX_ATTEMPTS:
                db.commit()
                # Let the outbox retry with its normal backoff.
                raise RuntimeError(
                    f"Push delivery failed (will retry): {result.errors[:3]}"
                )

            delivery.status = "FAILED"
            db.commit()
            logger.warning(
                "Booking push permanently failed event_id=%s result=%s",
                event_id, result.as_dict(),
            )
