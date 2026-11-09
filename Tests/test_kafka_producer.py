
from messageQueues.KafkaEventProducer import KafkaEventProducer

producer = KafkaEventProducer()

try:
    producer.publish(
        topic="stablebus.booking-events",
        key="TEST-BOOKING-001",
        event={
            "event_type": "TicketIssued",
            "booking_id": "TEST-BOOKING-001",
            "message": "This is a test event, not a real booking",
        },
    )
finally:
    producer.close()
