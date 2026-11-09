
import json
import os

from dotenv import load_dotenv
from kafka import KafkaProducer as KafkaClient

from .BaseProducer import BaseProducer


load_dotenv()


class KafkaEventProducer(BaseProducer):
    def __init__(self):
        self.topic = os.environ["KAFKA_BOOKING_TOPIC"]

        self.producer = KafkaClient(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            security_protocol="SASL_SSL",
            sasl_mechanism=os.getenv(
                "KAFKA_SASL_MECHANISM", "SCRAM-SHA-256"
            ),
            sasl_plain_username=os.environ["KAFKA_SASL_USERNAME"],
            sasl_plain_password=os.environ["KAFKA_SASL_PASSWORD"],
            ssl_cafile=os.environ["KAFKA_CA_CERT_PATH"],
            key_serializer=lambda key: key.encode("utf-8"),
            value_serializer=lambda event: json.dumps(event).encode("utf-8"),
            acks="all",
            retries=3,
        )

    def publish(self, topic: str, key: str, event: dict) -> None:
        future = self.producer.send(
            topic=topic,
            key=key,
            value=event,
        )

        # Wait for Kafka to acknowledge the message.
        metadata = future.get(timeout=15)

        print(
            f"Event published: topic={metadata.topic}, "
            f"partition={metadata.partition}, "
            f"offset={metadata.offset}"
        )

    def close(self) -> None:
        self.producer.flush(timeout=10)
        self.producer.close(timeout=10)
