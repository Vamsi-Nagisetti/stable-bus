import html
import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from core.database import SessionLocal
from models.NotificationDelivery import NotificationDelivery

logger = logging.getLogger(__name__)

EVENT_TYPE = "BOOKING_CONFIRMED"
CHANNEL = "EMAIL"


def _safe(value, fallback="—") -> str:
    value = fallback if value is None or value == "" else value
    return html.escape(str(value), quote=True)


def _format_date(value) -> str:
    if not value:
        return "—"

    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%A, %d %B %Y")
    except (TypeError, ValueError):
        try:
            from datetime import date

            return date.fromisoformat(str(value)).strftime("%A, %d %B %Y")
        except (TypeError, ValueError):
            return str(value)


def build_confirmation_email(payload: dict) -> tuple[str, str, str]:
    booking_id = payload.get("booking_id") or "—"
    pnr = payload.get("transport_pnr") or "Pending"
    supplier_ref = payload.get("supplier_refno") or "—"
    journey_date = _format_date(payload.get("journey_date"))
    amount = payload.get("total_amount") or "—"
    currency = payload.get("currency") or "INR"

    source = payload.get("source_city_name") or payload.get("source_city")
    destination = (
        payload.get("destination_city_name")
        or payload.get("destination_city")
    )

    bus_name = payload.get("bus_name") or payload.get("operator_name")
    bus_type = payload.get("bus_type")
    departure_time = payload.get("departure_time")
    arrival_time = payload.get("arrival_time")

    boarding = payload.get("boarding_point") or {}
    dropping = payload.get("dropping_point") or {}

    seats = payload.get("seat_numbers") or []
    seats_text = (
        ", ".join(str(seat) for seat in seats)
        if isinstance(seats, list)
        else str(seats)
    )

    passengers = payload.get("passengers") or []
    passenger_rows = []
    passenger_text_rows = []

    for passenger in passengers:
        name = _safe(passenger.get("name"), "Passenger")
        seat = _safe(passenger.get("seat_number"))
        ticket = _safe(passenger.get("ticket_number"))

        age = passenger.get("age")
        gender = passenger.get("gender")

        meta = " · ".join(
            str(value)
            for value in (age, gender)
            if value not in (None, "")
        )

        meta_html = (
            f'<div style="font-size:12px;color:#887A73;margin-top:4px">'
            f'{_safe(meta, "")}</div>'
            if meta
            else ""
        )

        passenger_rows.append(
            '<tr>'
            '<td style="padding:13px 12px;border-bottom:1px solid #EEE7E1">'
            f'<div style="font-weight:700;color:#382B28">{name}</div>'
            f'{meta_html}'
            '</td>'
            '<td style="padding:13px 12px;border-bottom:1px solid #EEE7E1;'
            f'color:#382B28">{seat}</td>'
            '<td style="padding:13px 12px;border-bottom:1px solid #EEE7E1;'
            f'color:#6F625D;font-size:12px">{ticket}</td>'
            '</tr>'
        )

        passenger_text_rows.append(
            f"{passenger.get('name') or 'Passenger'} | "
            f"Seat {passenger.get('seat_number') or '—'} | "
            f"Ticket {passenger.get('ticket_number') or '—'}"
        )

    if not passenger_rows:
        passenger_rows.append(
            '<tr><td colspan="3" style="padding:14px;color:#887A73">'
            'Passenger details unavailable</td></tr>'
        )

    def point_card(label, point):
        if not isinstance(point, dict) or not any(
            point.get(key)
            for key in ("name", "address", "landmark", "time", "reporting_time")
        ):
            return ""

        title = _safe(point.get("name"), label)
        address = _safe(point.get("address"))
        landmark = _safe(point.get("landmark"))
        time = _safe(point.get("reporting_time") or point.get("time"))

        details = "<br>".join(
            value
            for value in (
                address,
                f"Near {landmark}" if landmark != "—" else "",
                f"Time: {time}" if time != "—" else "",
            )
            if value
        )

        return (
            f'<td width="50%" valign="top" style="padding:14px;'
            f'background:#FFFEFC;border:1px solid #EAE0D7;border-radius:12px">'
            f'<div style="font-size:11px;letter-spacing:1px;'
            f'text-transform:uppercase;color:#887A73">{label}</div>'
            f'<div style="font-size:15px;font-weight:700;color:#382B28;'
            f'margin:6px 0">{title}</div>'
            f'<div style="font-size:12px;line-height:19px;'
            f'color:#6F625D">{details}</div>'
            '</td>'
        )

    point_cells = [
        value
        for value in (
            point_card("Boarding point", boarding),
            point_card("Dropping point", dropping),
        )
        if value
    ]

    points_section = ""

    if point_cells:
        points_section = (
            '<h3 style="font-size:16px;color:#382B28;margin:26px 0 10px">'
            'Your pickup & drop-off</h3>'
            '<table role="presentation" width="100%" cellspacing="0" '
            'cellpadding="0"><tr>'
            + "".join(point_cells)
            + '</tr></table>'
        )

    route = ""

    if source or destination:
        route = (
            f'<div style="font-size:19px;font-weight:700;color:#382B28">'
            f'{_safe(source, "Origin")} '
            f'<span style="color:#B18A88">→</span> '
            f'{_safe(destination, "Destination")}</div>'
        )

    schedule = " · ".join(
        value
        for value in (
            str(departure_time) if departure_time else "",
            f"Arrives {arrival_time}" if arrival_time else "",
        )
        if value
    )

    bus_line = " · ".join(
        str(value)
        for value in (bus_name, bus_type)
        if value
    )

    subject = f"Your StableBus ticket is confirmed · {booking_id}"

    email_html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>

<body style="margin:0;padding:0;background:#F8F4ED;
font-family:Arial,Helvetica,sans-serif;color:#382B28">

<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
style="background:#F8F4ED;padding:28px 12px">
<tr>
<td align="center">

<table role="presentation" width="600" cellspacing="0" cellpadding="0"
style="max-width:600px;width:100%;background:#FFFEFC;
border:1px solid #EAE0D7;border-radius:18px;overflow:hidden">

<tr>
<td style="background:#70404A;padding:26px 30px;color:#FFFEFC">
<div style="font-size:22px;font-weight:800;letter-spacing:.2px">
StableBus
</div>
<div style="font-size:12px;color:#F4EAEB;margin-top:5px;
letter-spacing:1.5px">
YOUR JOURNEY, CONFIRMED
</div>
</td>
</tr>

<tr>
<td style="padding:30px 30px 12px">

<div style="display:inline-block;background:#EAF2EC;color:#356B4A;
padding:7px 11px;border-radius:20px;font-size:12px;font-weight:700">
✓ &nbsp; TICKET CONFIRMED
</div>

<h1 style="font-size:25px;line-height:32px;margin:18px 0 8px;
color:#382B28">
You're all set to travel.
</h1>

<p style="font-size:14px;line-height:22px;color:#887A73;margin:0">
Your bus ticket has been confirmed. Keep this email handy for your journey.
</p>

<div style="margin-top:24px;padding:20px;background:#F8F4ED;
border:1px solid #EAE0D7;border-radius:14px">

{route}

<div style="font-size:13px;color:#887A73;margin-top:9px">
{_safe(journey_date)}
</div>

<div style="font-size:13px;color:#6F625D;margin-top:7px">
{_safe(bus_line, "Bus details unavailable")}
</div>

<div style="font-size:12px;color:#887A73;margin-top:5px">
{_safe(schedule, "")}
</div>

</div>

<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
style="margin-top:18px">

<tr>
<td width="50%" style="padding:12px 10px 12px 0;
border-bottom:1px solid #EEE7E1">
<div style="font-size:11px;color:#887A73;text-transform:uppercase;
letter-spacing:.8px">Booking ID</div>
<div style="font-size:13px;font-weight:700;margin-top:5px;
word-break:break-all">{_safe(booking_id)}</div>
</td>

<td width="50%" style="padding:12px 0 12px 10px;
border-bottom:1px solid #EEE7E1">
<div style="font-size:11px;color:#887A73;text-transform:uppercase;
letter-spacing:.8px">Operator PNR</div>
<div style="font-size:13px;font-weight:700;margin-top:5px">
{_safe(pnr)}
</div>
</td>
</tr>

<tr>
<td style="padding:12px 10px 12px 0;
border-bottom:1px solid #EEE7E1">
<div style="font-size:11px;color:#887A73;text-transform:uppercase;
letter-spacing:.8px">Seats</div>
<div style="font-size:13px;font-weight:700;margin-top:5px">
{_safe(seats_text)}
</div>
</td>

<td style="padding:12px 0 12px 10px;
border-bottom:1px solid #EEE7E1">
<div style="font-size:11px;color:#887A73;text-transform:uppercase;
letter-spacing:.8px">Total paid</div>
<div style="font-size:16px;font-weight:800;margin-top:4px;color:#783D4A">
{_safe(currency)} {_safe(amount)}
</div>
</td>
</tr>

</table>

{points_section}

<h3 style="font-size:16px;color:#382B28;margin:26px 0 10px">
Passenger details
</h3>

<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
style="border:1px solid #EAE0D7;border-radius:12px;
border-spacing:0;overflow:hidden">

<tr style="background:#F8F4ED">
<th align="left" style="padding:11px 12px;font-size:11px;
color:#887A73;text-transform:uppercase">Passenger</th>
<th align="left" style="padding:11px 12px;font-size:11px;
color:#887A73;text-transform:uppercase">Seat</th>
<th align="left" style="padding:11px 12px;font-size:11px;
color:#887A73;text-transform:uppercase">Ticket no.</th>
</tr>

{''.join(passenger_rows)}

</table>

<div style="margin-top:24px;padding:15px;background:#F4EAEB;
border-radius:12px;font-size:12px;line-height:19px;color:#65313E">
<strong>Before you travel</strong><br>
Please arrive at your boarding point ahead of the reporting time
and carry a valid photo ID.
</div>

<p style="font-size:13px;line-height:21px;color:#887A73;margin:24px 0 6px">
Thank you for choosing StableBus. We hope you have a comfortable journey.
</p>

<p style="font-size:13px;font-weight:700;color:#783D4A;margin:0 0 24px">
Team StableBus
</p>

</td>
</tr>

<tr>
<td style="padding:18px 30px;background:#FAF8F5;
border-top:1px solid #EAE0D7;font-size:11px;
line-height:18px;color:#887A73">
Booking reference: {_safe(supplier_ref)}<br>
This is an automated booking confirmation. Please do not reply to this email.
</td>
</tr>

</table>
</td>
</tr>
</table>

</body>
</html>'''

    text_lines = [
        "STABLEBUS — TICKET CONFIRMED",
        "",
        f"Route: {source or '—'} → {destination or '—'}",
        f"Journey date: {journey_date}",
        f"Bus: {bus_line or '—'}",
        f"Schedule: {schedule or '—'}",
        f"Booking ID: {booking_id}",
        f"Operator PNR: {pnr}",
        f"Operator reference: {supplier_ref}",
        f"Seats: {seats_text or '—'}",
        f"Total paid: {currency} {amount}",
        "",
        "PASSENGERS:",
        *(passenger_text_rows or ["Passenger details unavailable"]),
    ]

    for label, point in (
        ("BOARDING", boarding),
        ("DROPPING", dropping),
    ):
        if isinstance(point, dict) and point:
            text_lines.extend([
                "",
                f"{label}:",
                str(point.get("name") or "—"),
                str(point.get("address") or ""),
                str(
                    point.get("reporting_time")
                    or point.get("time")
                    or ""
                ),
            ])

    text_lines.extend([
        "",
        "Please arrive ahead of your boarding time and carry a valid photo ID.",
        "Thank you for choosing StableBus.",
    ])

    return subject, email_html, "\n".join(text_lines)


def is_permanent_email_error(error: Exception) -> bool:
    message = str(error).lower()

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