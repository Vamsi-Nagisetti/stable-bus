import html
import logging
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from core.database import SessionLocal
from models.NotificationDelivery import NotificationDelivery

logger = logging.getLogger(__name__)

EVENT_TYPE = "BOOKING_CONFIRMED"
CHANNEL = "EMAIL"

# ---- StableBus palette (same as the app) ----
BG = "#F8F4ED"
PAPER = "#FFFEFC"
INK = "#382B28"
MUTED = "#887A73"
BORDER = "#EAE0D7"
BURGUNDY = "#783D4A"
BURGUNDY_DARK = "#65313E"
BURGUNDY_LIGHT = "#F4EAEB"
GREEN = "#356B4A"
GREEN_LIGHT = "#EAF2EC"
FONT = "Arial,Helvetica,sans-serif"


def _safe(value, fallback="—") -> str:
    value = fallback if value is None or value == "" else value
    return html.escape(str(value), quote=True)


def _clean(value, default: str = "") -> str:
    text = "" if value is None else str(value).strip()
    return text or default


def _format_date(value) -> str:
    if not value:
        return "—"

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%a, %d %b %Y")
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(str(value)).strftime("%a, %d %b %Y")
        except (TypeError, ValueError):
            return str(value)


def _format_money(currency, amount) -> str:
    raw = _clean(amount)
    if not raw:
        return "—"
    code = _clean(currency, "INR")
    try:
        number = float(raw)
        shown = f"{int(number):,}" if number == int(number) else f"{number:,.2f}"
    except ValueError:
        shown = raw
    return f"₹{shown}" if code.upper() == "INR" else f"{code} {shown}"


def _label(text: str) -> str:
    return (
        f'<div style="font-size:11px;color:{MUTED};text-transform:uppercase;'
        f'letter-spacing:.8px;font-family:{FONT}">{_safe(text)}</div>'
    )


def _grid_cell(label: str, value_html: str, padding: str) -> str:
    return (
        f'<td width="50%" valign="top" style="padding:{padding};'
        f'border-bottom:1px solid #EEE7E1">{_label(label)}'
        f'<div style="margin-top:5px;font-family:{FONT}">{value_html}</div></td>'
    )


def _route_html(source, destination) -> str:
    if not (source or destination):
        return ""
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse"><tr>'
        f'<td align="left" valign="middle" style="font-family:{FONT};font-size:20px;'
        f'font-weight:700;color:{INK}">{_safe(source, "Origin")}</td>'
        f'<td align="center" valign="middle" width="56" style="font-family:{FONT};'
        f'font-size:20px;color:{BURGUNDY}">&rarr;</td>'
        f'<td align="right" valign="middle" style="font-family:{FONT};font-size:20px;'
        f'font-weight:700;color:{INK}">{_safe(destination, "Destination")}</td>'
        '</tr></table>'
    )


def _point_details(point: dict) -> dict:
    name = _clean(point.get("name"))
    address = _clean(point.get("address"))
    landmark = _clean(point.get("landmark"))
    when = _clean(point.get("reporting_time") or point.get("time"))

    # Operators often repeat the name inside the address / landmark: show it once.
    if address.lower() == name.lower():
        address = ""
    if landmark.lower() in (name.lower(), address.lower(), "n/a"):
        landmark = ""

    return {"name": name, "address": address, "landmark": landmark, "time": when}


def _point_cell(label: str, point, padding: str) -> str:
    details = _point_details(point if isinstance(point, dict) else {})
    parts = [
        _label(label),
        f'<div style="font-size:14px;font-weight:700;color:{INK};margin-top:6px;'
        f'font-family:{FONT}">{_safe(details["name"], label)}</div>',
    ]
    if details["address"]:
        parts.append(
            f'<div style="font-size:12px;line-height:18px;color:{MUTED};margin-top:3px;'
            f'font-family:{FONT}">{_safe(details["address"])}</div>'
        )
    if details["landmark"]:
        parts.append(
            f'<div style="font-size:12px;line-height:18px;color:{MUTED};margin-top:2px;'
            f'font-family:{FONT}">Near {_safe(details["landmark"])}</div>'
        )
    if details["time"]:
        parts.append(
            f'<div style="font-size:13px;font-weight:700;color:{BURGUNDY};margin-top:6px;'
            f'font-family:{FONT}">{_safe(details["time"])}</div>'
        )
    return f'<td width="50%" valign="top" style="padding:{padding}">{"".join(parts)}</td>'


def _has_point(point) -> bool:
    return isinstance(point, dict) and any(
        point.get(key) for key in ("name", "address", "landmark", "time", "reporting_time")
    )


def build_confirmation_email(payload: dict) -> tuple[str, str, str]:
    booking_id = payload.get("booking_id") or "—"
    pnr = payload.get("transport_pnr") or "Pending"
    supplier_ref = payload.get("supplier_refno") or "—"
    journey_date = _format_date(payload.get("journey_date"))
    money = _format_money(payload.get("currency"), payload.get("total_amount"))

    # Bus details are also kept inside boarding_point["_bus"] by the app.
    _raw_point = payload.get("boarding_point")
    bus_info = (_raw_point.get("_bus") if isinstance(_raw_point, dict) else None) or {}

    source = payload.get("source_city_name") or bus_info.get("source_city_name") or payload.get("source_city")
    destination = (
        payload.get("destination_city_name")
        or bus_info.get("destination_city_name")
        or payload.get("destination_city")
    )

    bus_name = (
        payload.get("operator_name")
        or bus_info.get("operator_name")
        or payload.get("bus_name")
        or payload.get("travel_name")
        or payload.get("operator")
    )
    bus_type = payload.get("bus_type") or bus_info.get("bus_type")
    departure_time = payload.get("departure_time") or bus_info.get("departure_time")
    arrival_time = payload.get("arrival_time") or bus_info.get("arrival_time")

    boarding = payload.get("boarding_point") or {}
    dropping = payload.get("dropping_point") or {}

    seats = payload.get("seat_numbers") or []
    seats_text = (
        ", ".join(str(seat) for seat in seats)
        if isinstance(seats, list)
        else str(seats)
    )

    # ---------- passengers ----------
    passenger_rows = []
    passenger_text_rows = []

    for index, passenger in enumerate(payload.get("passengers") or [], start=1):
        full_name = " ".join(
            part
            for part in (_clean(passenger.get("title")), _clean(passenger.get("name")))
            if part
        ) or f"Passenger {index}"
        seat = _clean(passenger.get("seat_number"))
        ticket = _clean(passenger.get("ticket_number"))

        age = _clean(passenger.get("age"))
        gender = _clean(passenger.get("gender"))
        meta = " · ".join(
            part for part in (f"{age} yrs" if age else "", gender) if part
        )

        meta_html = (
            f'<div style="font-size:12px;color:{MUTED};margin-top:3px">{_safe(meta, "")}</div>'
            if meta
            else ""
        )

        passenger_rows.append(
            "<tr>"
            f'<td valign="middle" style="padding:13px 12px;border-top:1px solid {BORDER};font-family:{FONT}">'
            f'<div style="font-size:14px;font-weight:700;color:{INK}">{_safe(full_name)}</div>'
            f"{meta_html}</td>"
            f'<td valign="middle" align="center" width="64" style="padding:13px 6px;border-top:1px solid {BORDER};font-family:{FONT}">'
            f'<span style="display:inline-block;min-width:34px;padding:6px 10px;background:{BURGUNDY_LIGHT};'
            f'color:{BURGUNDY};border-radius:8px;font-size:13px;font-weight:700;text-align:center">'
            f"{_safe(seat)}</span></td>"
            f'<td valign="middle" align="right" style="padding:13px 12px;border-top:1px solid {BORDER};'
            f'font-family:{FONT};font-size:12px;color:{MUTED}">{_safe(ticket)}</td>'
            "</tr>"
        )

        text_bits = [full_name]
        if meta:
            text_bits.append(meta)
        text_bits.append(f"Seat {seat or '—'}")
        text_bits.append(f"Ticket {ticket or '—'}")
        passenger_text_rows.append("  " + " | ".join(text_bits))

    if not passenger_rows:
        passenger_rows.append(
            f'<tr><td colspan="3" style="padding:14px 12px;font-size:13px;color:{MUTED};'
            f'font-family:{FONT};border-top:1px solid {BORDER}">Passenger details unavailable</td></tr>'
        )

    # ---------- pickup & drop-off ----------
    points_section = ""

    if _has_point(boarding) or _has_point(dropping):
        points_section = (
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="margin-top:20px;border:1px solid {BORDER};border-radius:14px;'
            f'border-collapse:separate;background:{PAPER}"><tr>'
            + _point_cell("Boarding", boarding, "16px 10px 16px 16px")
            + _point_cell("Dropping", dropping, "16px 16px 16px 10px")
            + "</tr></table>"
        )

    route = _route_html(source, destination)

    schedule = " · ".join(
        value
        for value in (
            f"Departs {departure_time}" if departure_time else "",
            f"Arrives {arrival_time}" if arrival_time else "",
        )
        if value
    )

    bus_line = " · ".join(
        str(value)
        for value in (bus_name, bus_type)
        if value
    )

    if source and destination:
        subject = f"Your StableBus ticket is confirmed · {source} → {destination}"
    else:
        subject = f"Your StableBus ticket is confirmed · {booking_id}"

    preheader = f"{journey_date} · Seats {seats_text or '—'} · PNR {pnr}"

    schedule_html = (
        f'<div style="font-size:12px;color:{MUTED};margin-top:4px">{_safe(schedule)}</div>'
        if schedule
        else ""
    )

    email_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Your StableBus ticket</title>
</head>
<body style="margin:0;padding:0;background:{BG};font-family:{FONT};color:{INK}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{BG}">{_safe(preheader)}</div>

<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{BG};padding:28px 12px">
<tr><td align="center">

<table role="presentation" width="600" cellspacing="0" cellpadding="0"
       style="max-width:600px;width:100%;background:{PAPER};border:1px solid {BORDER};border-radius:18px;overflow:hidden">

  <tr>
    <td style="background:{BURGUNDY};padding:26px 30px;color:{PAPER};font-family:{FONT}">
      <div style="font-size:22px;font-weight:800;letter-spacing:.2px">StableBus</div>
      <div style="font-size:12px;color:{BURGUNDY_LIGHT};margin-top:5px;letter-spacing:1.5px">YOUR JOURNEY, CONFIRMED</div>
    </td>
  </tr>

  <tr>
    <td style="padding:30px 30px 8px;font-family:{FONT}">

      <span style="display:inline-block;background:{GREEN_LIGHT};color:{GREEN};padding:7px 12px;border-radius:20px;font-size:12px;font-weight:700">
        &#10003;&nbsp; TICKET CONFIRMED
      </span>

      <h1 style="font-size:25px;line-height:32px;margin:18px 0 8px;color:{INK};font-family:{FONT}">You&rsquo;re all set to travel.</h1>
      <p style="font-size:14px;line-height:22px;color:{MUTED};margin:0">
        Your bus ticket has been confirmed. Keep this email handy for your journey.
      </p>

      <div style="margin-top:24px;padding:20px;background:{BG};border:1px solid {BORDER};border-radius:14px">
        {route}
        <div style="font-size:13px;color:{MUTED};margin-top:10px">{_safe(journey_date)}</div>
        {f'<div style="font-size:17px;font-weight:700;color:#783D4A;margin-bottom:6px;font-family:{FONT}">{_safe(bus_name)}</div>' if bus_name else ''}
        {f'<div style="font-size:13px;color:#6F625D;margin-top:8px">{_safe(bus_type)}</div>' if bus_type else ''}
        {schedule_html}
      </div>

      {points_section}

      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:18px;border-collapse:collapse">
        <tr>
          {_grid_cell("Booking ID", f'<span style="font-size:13px;font-weight:700;color:{INK};word-break:break-all">{_safe(booking_id)}</span>', "12px 10px 12px 0")}
          {_grid_cell("Operator PNR", f'<span style="font-size:15px;font-weight:800;color:{BURGUNDY}">{_safe(pnr)}</span>', "12px 0 12px 10px")}
        </tr>
        <tr>
          {_grid_cell("Seats", f'<span style="font-size:13px;font-weight:700;color:{INK}">{_safe(seats_text)}</span>', "12px 10px 12px 0")}
          {_grid_cell("Total paid", f'<span style="font-size:18px;font-weight:800;color:{BURGUNDY}">{_safe(money)}</span>', "12px 0 12px 10px")}
        </tr>
      </table>

      <h3 style="font-size:16px;color:{INK};margin:26px 0 10px;font-family:{FONT}">Passenger details</h3>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="border:1px solid {BORDER};border-radius:12px;border-collapse:separate;border-spacing:0;overflow:hidden">
        <tr style="background:{BG}">
          <th align="left" style="padding:11px 12px;font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.6px;font-family:{FONT}">Passenger</th>
          <th align="center" style="padding:11px 6px;font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.6px;font-family:{FONT}">Seat</th>
          <th align="right" style="padding:11px 12px;font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.6px;font-family:{FONT}">Ticket no.</th>
        </tr>
        {"".join(passenger_rows)}
      </table>

      <div style="margin-top:24px;padding:15px 16px;background:{BURGUNDY_LIGHT};border-radius:12px;font-size:13px;line-height:20px;color:{BURGUNDY_DARK}">
        <strong>Before you travel</strong><br>
        Please arrive at your boarding point ahead of the reporting time and carry a valid photo ID.
      </div>

      <p style="font-size:13px;line-height:21px;color:{MUTED};margin:24px 0 6px">
        Thank you for choosing StableBus. We hope you have a comfortable journey.
      </p>
      <p style="font-size:13px;font-weight:700;color:{BURGUNDY};margin:0 0 26px">Team StableBus</p>
    </td>
  </tr>

  <tr>
    <td style="padding:18px 30px;background:#FAF8F5;border-top:1px solid {BORDER};font-size:11px;line-height:18px;color:{MUTED};font-family:{FONT}">
      Operator reference: {_safe(supplier_ref)}<br>
      This is an automated booking confirmation. Please do not reply to this email.
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    # ---------- plain text ----------
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
        f"Total paid: {money}",
        "",
        "PASSENGERS:",
        *(passenger_text_rows or ["Passenger details unavailable"]),
    ]

    for label, point in (
        ("BOARDING", boarding),
        ("DROPPING", dropping),
    ):
        if isinstance(point, dict) and point:
            details = _point_details(point)
            text_lines.extend(
                ["", f"{label}:", details["name"] or "—"]
                + [
                    value
                    for value in (
                        details["address"],
                        f"Near {details['landmark']}" if details["landmark"] else "",
                        details["time"],
                    )
                    if value
                ]
            )

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