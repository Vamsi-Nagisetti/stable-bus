
import html
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from core.database import SessionLocal
from models.NotificationDelivery import NotificationDelivery
from messageQueues.KafkaEventConsumer import KafkaEventConsumer
from Adaptors.Notifications.ResendEmailAdapter import ResendEmailAdapter
from Services.Notifications.NotificationService import NotificationService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

CHANNEL = "EMAIL"
EVENT_TYPE = "BOOKING_CONFIRMED"


def build_confirmation_email(payload: dict) -> tuple[str, str, str]:
    pnr = str(payload.get("transport_pnr") or "N/A")
    journey_date = str(payload.get("journey_date") or "N/A")
    seats = payload.get("seat_numbers") or []

    if isinstance(seats, list):
        seat_text = ", ".join(str(seat) for seat in seats)
    else:
        seat_text = str(seats)

    passengers = payload.get("passengers") or []
    passenger_names = [
        str(p.get("name"))
        for p in passengers
        if isinstance(p, dict) and p.get("name")
    ]

    passenger_text = (
        ", ".join(passenger_names) if passenger_names else "As per booking"
    )

    amount = payload.get("total_amount")
    currency = payload.get("currency") or "INR"
    amount_text = f"{currency} {amount}" if amount is not None else "N/A"

    safe_pnr = html.escape(pnr)
    safe_date = html.escape(journey_date)
    safe_seats = html.escape(seat_text or "N/A")
    safe_passengers = html.escape(passenger_text)
    safe_amount = html.escape(amount_text)

    subject = f"Your StableBus booking is confirmed - PNR {pnr}"

    text = f"""
Your StableBus booking is confirmed!

PNR: {pnr}
Journey date: {journey_date}
Seats: {seat_text or "N/A"}
Passengers: {passenger_text}
Amount: {amount_text}

Thank you for choosing StableBus.
"""

    email_html = f"""
    <div style="font-family: Arial, sans-serif; color: #382B28;
                max-width: 600px; margin: auto; padding: 24px;">
        <h2 style="color: #783D4A;">Booking confirmed!</h2>
        <p>Your StableBus booking has been confirmed successfully.</p>

        <div style="background: #F8F4ED; padding: 20px;
                    border-radius: 12px;">
            <p><strong>PNR:</strong> {safe_pnr}</p>
            <p><strong>Journey date:</strong> {safe_date}</p>
            <p><strong>Seats:</strong> {safe_seats}</p>
            <p><strong>Passengers:</strong> {safe_passengers}</p>
            <p><strong>Amount:</strong> {safe_amount}</p>
        </div>

        <p>Thank you for choosing StableBus.</p>
        <p>Have a safe journey!</p>
        <p style="color: #887A73;">Team StableBus</p>
    </div>
    """

    return subject, email_html, text


def get_or_create_delivery(event_id: str) -> NotificationDelivery:
    with SessionLocal() as db:
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
            db.commit()
            db.refresh(delivery)

        return delivery


def mark_delivery_sent(event_id: str) -> None:
    with SessionLocal() as db:
        delivery = db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.event_id == event_id,
                NotificationDelivery.channel == CHANNEL,
            )
        ).scalar_one()

        delivery.status = "SENT"
        delivery.sent_at = datetime.now(timezone.utc)
        delivery.last_error = None

        db.commit()


def record_delivery_failure(event_id: str, error: Exception) -> int:
    with SessionLocal() as db:
        delivery = db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.event_id == event_id,
                NotificationDelivery.channel == CHANNEL,
            )
        ).scalar_one()

        delivery.attempts += 1
        delivery.last_error = str(error)[:2000]

        db.commit()
        return delivery.attempts


def mark_delivery_failed(event_id: str, error: str) -> None:
    with SessionLocal() as db:
        delivery = db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.event_id == event_id,
                NotificationDelivery.channel == CHANNEL,
            )
        ).scalar_one()

        delivery.status = "FAILED"
        delivery.last_error = error[:2000]

        db.commit()


def is_permanent_email_error(error: Exception) -> bool:
    """
    Treat HTTP 4xx errors as permanent, except 429 (rate limit).
    Supports both exceptions exposing status_code and the
    RuntimeError message currently raised by ResendEmailAdapter.
    """
    status_code = getattr(error, "status_code", None)

    if status_code is None:
        error_text = str(error)

        for code in range(400, 500):
            if code == 429:
                continue

            if f"HTTP {code}" in error_text:
                return True

        return False

    return 400 <= status_code < 500 and status_code != 429


def process_message(message, consumer, notification_service) -> None:
    event = message.value

    event_id = event.get("event_id")
    event_type = event.get("event_type")
    payload = event.get("payload") or {}

    if not event_id:
        raise ValueError("Kafka event is missing event_id")

    if event_type != EVENT_TYPE:
        logger.warning(
            "Skipping unsupported event type=%s event_id=%s",
            event_type,
            event_id,
        )
        consumer.commit()
        return

    delivery = get_or_create_delivery(event_id)

    if delivery.status == "SENT":
        logger.info(
            "Email already sent. Skipping duplicate event_id=%s",
            event_id,
        )
        consumer.commit()
        return

    customer_email = payload.get("customer_email")

    if not customer_email:
        error = "Booking confirmation event has no customer_email"
        mark_delivery_failed(event_id, error)

        logger.error("%s. event_id=%s", error, event_id)
        consumer.commit()
        return

    subject, email_html, email_text = build_confirmation_email(payload)

    while True:
        try:
            notification_service.send_email(
                to_email=customer_email,
                subject=subject,
                html=email_html,
                text=email_text,
            )

            mark_delivery_sent(event_id)

            # Commit only after PostgreSQL records SENT.
            consumer.commit()

            logger.info(
                "Confirmation email sent. event_id=%s recipient=%s",
                event_id,
                customer_email,
            )
            return

        except Exception as exc:
            attempts = record_delivery_failure(event_id, exc)

            if is_permanent_email_error(exc):
                mark_delivery_failed(event_id, str(exc))

                logger.error(
                    "Permanent email delivery failure. "
                    "Skipping Kafka record. event_id=%s "
                    "recipient=%s attempts=%s error=%s",
                    event_id,
                    customer_email,
                    attempts,
                    exc,
                )

                # Acknowledge permanently invalid messages.
                # This allows the consumer to reach subsequent offsets.
                consumer.commit()
                return

            delay = min(5 * (2 ** (attempts - 1)), 300)

            logger.exception(
                "Transient email delivery failure. "
                "event_id=%s attempt=%s retry_in=%ss",
                event_id,
                attempts,
                delay,
            )

            time.sleep(delay)


def main():
    consumer = KafkaEventConsumer()
    notification_provider = ResendEmailAdapter()
    notification_service = NotificationService(notification_provider)

    logger.info("StableBus notification worker started")

    try:
        while True:
            message = consumer.consume(timeout=10.0)

            if message is None:
                continue

            process_message(
                message=message,
                consumer=consumer,
                notification_service=notification_service,
            )

    except KeyboardInterrupt:
        logger.info("Notification worker stopping")

    finally:
        consumer.close()
        notification_service.close()
        logger.info("Notification worker stopped")


if __name__ == "__main__":
    main()
