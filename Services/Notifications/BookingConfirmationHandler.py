
import html
import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from core.database import SessionLocal
from models.NotificationDelivery import NotificationDelivery

logger = logging.getLogger(__name__)

EVENT_TYPE = "BOOKING_CONFIRMED"
CHANNEL = "EMAIL"


def build_confirmation_email(payload: dict) -> tuple[str, str, str]:
    booking_id = payload.get("booking_id", "N/A")
    pnr = payload.get("transport_pnr") or "Pending"
    supplier_ref = payload.get("supplier_refno") or "N/A"
    journey_date = payload.get("journey_date") or "N/A"
    amount = payload.get("total_amount") or "N/A"
    currency = payload.get("currency") or "INR"

    seats = payload.get("seat_numbers") or []
    if isinstance(seats, list):
        seats_text = ", ".join(str(seat) for seat in seats)
    else:
        seats_text = str(seats)

    passengers = payload.get("passengers") or []
    passenger_lines = []

    for passenger in passengers:
        name = html.escape(str(passenger.get("name") or "Passenger"))
        seat = html.escape(str(passenger.get("seat_number") or "N/A"))
        ticket = html.escape(str(passenger.get("ticket_number") or "N/A"))

        passenger_lines.append(
            f"<li>{name} — Seat: {seat} — Ticket: {ticket}</li>"
        )

    passenger_html = "".join(passenger_lines) or "<li>Not available</li>"

    safe_booking_id = html.escape(str(booking_id))
    safe_pnr = html.escape(str(pnr))
    safe_supplier_ref = html.escape(str(supplier_ref))
    safe_journey_date = html.escape(str(journey_date))
    safe_amount = html.escape(str(amount))
    safe_currency = html.escape(str(currency))
    safe_seats = html.escape(seats_text)

    subject = f"StableBus Booking Confirmed - {booking_id}"

    email_html = f"""
    <html>
      <body>
        <h2>Your bus booking is confirmed!</h2>
        <p>Thank you for booking with StableBus.</p>

        <h3>Booking details</h3>
        <p><strong>Booking ID:</strong> {safe_booking_id}</p>
        <p><strong>PNR:</strong> {safe_pnr}</p>
        <p><strong>Operator Reference:</strong> {safe_supplier_ref}</p>
        <p><strong>Journey Date:</strong> {safe_journey_date}</p>
        <p><strong>Seats:</strong> {safe_seats}</p>
        <p><strong>Amount:</strong> {safe_currency} {safe_amount}</p>

        <h3>Passengers</h3>
        <ul>{passenger_html}</ul>

        <p>Have a safe journey!</p>
        <p>Team StableBus</p>
      </body>
    </html>
    """

    email_text = (
        f"Your StableBus booking is confirmed!\n\n"
        f"Booking ID: {booking_id}\n"
        f"PNR: {pnr}\n"
        f"Operator Reference: {supplier_ref}\n"
        f"Journey Date: {journey_date}\n"
        f"Seats: {seats_text}\n"
        f"Amount: {currency} {amount}\n\n"
        "Thank you for booking with StableBus."
    )

    return subject, email_html, email_text


def is_permanent_email_error(error: Exception) -> bool:
    message = str(error).lower()

    # Resend adapter currently wraps request errors in RuntimeError.
    # Inspect the original exception chain for HTTP response status.
    current = error

    while current is not None:
        response = getattr(current, "response", None)
        status_code = getattr(response, "status_code", None)

        if status_code is not None:
            return 400 <= status_code < 500 and status_code != 429

        current = current.__cause__ or current.__context__

    return isinstance(error, ValueError) or (
        "invalid recipient" in message
        or "cannot be empty" in message
    )


class BookingConfirmationHandler:

    def __init__(self, notification_service):
        self.notification_service = notification_service

    def _get_or_create_delivery(self, event_id: str) -> str:
        with SessionLocal() as db:
            status = db.execute(
                select(NotificationDelivery.status).where(
                    NotificationDelivery.event_id == event_id,
                    NotificationDelivery.channel == CHANNEL,
                )
            ).scalar_one_or_none()

            if status is not None:
                return status

            delivery = NotificationDelivery(
                event_id=event_id,
                channel=CHANNEL,
                status="PENDING",
                attempts=0,
            )

            db.add(delivery)

            try:
                db.commit()
                return "PENDING"
            except IntegrityError:
                db.rollback()

                status = db.execute(
                    select(NotificationDelivery.status).where(
                        NotificationDelivery.event_id == event_id,
                        NotificationDelivery.channel == CHANNEL,
                    )
                ).scalar_one_or_none()

                if status is None:
                    raise

                return status

    def _mark_sent(self, event_id: str) -> None:
        from datetime import datetime, timezone

        with SessionLocal() as db:
            db.execute(
                update(NotificationDelivery)
                .where(
                    NotificationDelivery.event_id == event_id,
                    NotificationDelivery.channel == CHANNEL,
                )
                .values(
                    status="SENT",
                    sent_at=datetime.now(timezone.utc),
                    last_error=None,
                )
            )
            db.commit()

    def _record_failure(self, event_id: str, error: Exception) -> None:
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

    def _mark_failed(self, event_id: str, error: Exception) -> None:
        with SessionLocal() as db:
            db.execute(
                update(NotificationDelivery)
                .where(
                    NotificationDelivery.event_id == event_id,
                    NotificationDelivery.channel == CHANNEL,
                )
                .values(
                    status="FAILED",
                    last_error=str(error)[:2000],
                )
            )
            db.commit()

    def __call__(self, event: dict) -> None:
        event_id = event.get("event_id")
        event_type = event.get("event_type")

        if not event_id:
            raise ValueError("Event is missing event_id")

        if event_type != EVENT_TYPE:
            logger.warning(
                "Ignoring unsupported event type: %s",
                event_type,
            )
            return

        status = self._get_or_create_delivery(event_id)

        if status in ("SENT", "FAILED"):
            logger.info(
                "Skipping terminal notification delivery: event_id=%s status=%s",
                event_id,
                status,
            )
            return

        payload = event.get("payload") or {}
        customer_email = payload.get("customer_email")

        if not customer_email:
            error = ValueError(
                "Booking confirmation event has no customer_email"
            )
            self._record_failure(event_id, error)
            self._mark_failed(event_id, error)

            logger.warning(
                "Notification permanently failed: event_id=%s",
                event_id,
            )
            return

        subject, email_html, email_text = build_confirmation_email(payload)

        try:
            self.notification_service.send_email(
                to_email=customer_email,
                subject=subject,
                html=email_html,
                text=email_text,
            )

            self._mark_sent(event_id)

            logger.info(
                "Booking confirmation email sent: event_id=%s",
                event_id,
            )

        except Exception as exc:
            self._record_failure(event_id, exc)

            if is_permanent_email_error(exc):
                self._mark_failed(event_id, exc)

                logger.error(
                    "Permanent email failure: event_id=%s error=%s",
                    event_id,
                    exc,
                )
                return

            logger.exception(
                "Transient email failure: event_id=%s",
                event_id,
            )
            raise
