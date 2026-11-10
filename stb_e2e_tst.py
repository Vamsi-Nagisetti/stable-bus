"""
StableBus guest checkout E2E test.

Prerequisites:
1. FastAPI is running at BASE_URL.
2. APP_ENV=development
3. BUS_BOOKING_PROVIDER=MOCK
4. PAYMENT_GATEWAY=MOCK
5. Save the supplied create-booking JSON as booking_payload.json
   in the same folder as this script.
6. Add the development-only mock-payment endpoint shown in the chat.

Run:
    pip install requests
    python stablebus_e2e_test.py
"""

import json
import os
import sys
import uuid
from pathlib import Path

import requests

BASE_URL = os.getenv("STABLEBUS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PAYLOAD_FILE = Path(__file__).with_name("booking_payload.json")
TIMEOUT = 45


def fail(message):
    print(f"\n[FAIL] {message}")
    sys.exit(1)


def request_json(method, path, *, headers=None, body=None):
    url = f"{BASE_URL}{path}"
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=body,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        fail(f"{method} {path}: {exc}")

    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    print(f"\n{method} {path} -> HTTP {response.status_code}")
    print(json.dumps(data, indent=2, default=str))

    if not response.ok:
        fail(f"Request failed: {method} {path} (HTTP {response.status_code})")
    if not isinstance(data, dict):
        fail(f"Expected JSON object from {method} {path}")
    return data


def require(data, key, step):
    value = data.get(key)
    if value in (None, ""):
        fail(f"{step}: response is missing '{key}'")
    return value


def main():
    if not PAYLOAD_FILE.exists():
        fail(
            f"Missing {PAYLOAD_FILE.name}. Save your supplied create-booking "
            "JSON in this file beside the script."
        )

    with PAYLOAD_FILE.open("r", encoding="utf-8") as file:
        booking_payload = json.load(file)

    # Ensure every run creates a fresh booking instead of reusing an
    # earlier idempotent request.
    booking_payload["idempotency_key"] = f"e2e-{uuid.uuid4()}"

    print("=" * 65)
    print("STABLEBUS GUEST CHECKOUT E2E TEST")
    print(f"API: {BASE_URL}")
    print("=" * 65)

    # 1. Create temporary booking.
    created = request_json(
        "POST",
        "/api/v1/bookings",
        body=booking_payload,
    )
    booking_id = require(created, "booking_id", "Create booking")
    guest_token = require(created, "guest_access_token", "Create booking")

    print(f"\n[PASS] Booking created: {booking_id}")
    headers = {"X-Guest-Access-Token": guest_token}

    # 2. Initiate payment.
    payment_init = request_json(
        "POST",
        f"/api/v1/bookings/{booking_id}/payments",
        headers=headers,
        body={"idempotency_key": f"payment-e2e-{uuid.uuid4()}"},
    )
    payment_id = require(payment_init, "payment_id", "Initiate payment")
    gateway_order_id = require(
        payment_init, "gateway_order_id", "Initiate payment"
    )

    if str(payment_init.get("status", "")).upper() != "PENDING":
        fail(f"Expected payment status PENDING, got {payment_init.get('status')}")

    print(f"\n[PASS] Payment initiated: {payment_id}")

    # 3. Simulate successful payment inside the running API process.
    simulated = request_json(
        "POST",
        f"/api/v1/bookings/test/mock-payments/{gateway_order_id}/mock-success",
    )
    gateway_payment_id = require(
        simulated, "gateway_payment_id", "Mock payment simulation"
    )
    print(f"\n[PASS] Mock payment simulated: {gateway_payment_id}")

    # 4. Verify payment.
    verified = request_json(
        "POST",
        f"/api/v1/bookings/{booking_id}/payments/verify",
        headers=headers,
        body={
            "payment_id": payment_id,
            "gateway_payment_id": gateway_payment_id,
            "signature": "mock-signature",
        },
    )
    if str(verified.get("status", "")).upper() != "SUCCESS":
        fail(f"Payment verification did not succeed: {verified}")
    if str(verified.get("booking_status", "")).upper() != "PAYMENT_VERIFIED":
        fail(f"Expected booking PAYMENT_VERIFIED: {verified}")

    print("\n[PASS] Payment verified")

    # 5. Submit ticketing request.
    ticketing = request_json(
        "POST",
        f"/api/v1/bookings/{booking_id}/ticketing",
        headers=headers,
    )
    ticketing_status = str(ticketing.get("booking_status", "")).upper()
    if ticketing_status not in {"TICKETING_UNKNOWN", "TICKETING_PENDING"}:
        fail(f"Unexpected ticketing status: {ticketing_status}")

    print(f"\n[PASS] Ticketing submitted: {ticketing_status}")

    # 6. Requery until the mock provider confirms the ticket.
    requery = request_json(
        "POST",
        f"/api/v1/bookings/{booking_id}/requery",
        headers=headers,
    )
    final_status = str(requery.get("booking_status", "")).upper()
    if final_status != "CONFIRMED":
        fail(
            "Booking was not confirmed by requery. "
            f"Current status: {final_status}. Check provider response/logs."
        )

    print("\n[PASS] Booking confirmed")
    print(f"Booking ID: {booking_id}")
    print(f"PNR: {requery.get('transport_pnr')}")

    print("\n" + "=" * 65)
    print("E2E FLOW PASSED")
    print("=" * 65)
    print("\nNow verify the transactional Outbox event in PostgreSQL:")
    print(
        "SELECT id, aggregate_id, event_type, status, attempts "
        "FROM outbox_events "
        f"WHERE aggregate_id = '{booking_id}' "
        "ORDER BY created_at DESC;"
    )
    print("\nExpected: BOOKING_CONFIRMED | PENDING | 0")


if __name__ == "__main__":
    main()
