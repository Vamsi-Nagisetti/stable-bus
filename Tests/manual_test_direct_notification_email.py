
import logging
import os
import uuid

from dotenv import load_dotenv

from Factories.EventTransportFactory import create_event_transport

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

RECIPIENT_EMAIL = "vamsinagisetti22@gmail.com"


def main():
    transport = os.getenv("EVENT_TRANSPORT", "direct").strip().lower()

    if transport != "direct":
        raise RuntimeError(
            "This test is specifically for direct transport. "
            "Set EVENT_TRANSPORT=direct in your .env"
        )

    dispatcher = None
    resources = []

    event_id = str(uuid.uuid4())
    booking_id = f"SB-TEST-{uuid.uuid4().hex[:8].upper()}"

    event = {
        "event_id": event_id,
        "event_type": "BOOKING_CONFIRMED",
        "aggregate_type": "BOOKING",
        "aggregate_id": booking_id,
        "payload": {
            "booking_id": booking_id,
            "customer_email": RECIPIENT_EMAIL,
            "transport_pnr": "TESTPNR123",
            "supplier_refno": "TEST-OPERATOR-001",
            "journey_date": "2026-11-20",
            "seat_numbers": ["12", "13"],
            "total_amount": 1200,
            "currency": "INR",
            "passengers": [
                {
                    "name": "Test Passenger 1",
                    "seat_number": "12",
                    "ticket_number": "TKT-001",
                },
                {
                    "name": "Test Passenger 2",
                    "seat_number": "13",
                    "ticket_number": "TKT-002",
                },
            ],
        },
    }

    try:
        dispatcher, resources = create_event_transport()

        print("\nStarting real email delivery test...")
        print(f"Recipient: {RECIPIENT_EMAIL}")
        print(f"Booking ID: {booking_id}")
        print(f"Event ID: {event_id}\n")

        dispatcher.publish(
            topic=dispatcher.topic,
            key=booking_id,
            event=event,
        )

        print("SUCCESS: Direct notification handler completed.")
        print(f"Email submitted to Resend: {RECIPIENT_EMAIL}")
        print(f"Event ID: {event_id}")

    except Exception:
        logging.exception("Direct notification email test failed.")
        raise

    finally:
        if dispatcher is not None:
            dispatcher.close()

        for resource in resources:
            resource.close()


if __name__ == "__main__":
    main()
