
import json
import os

from dotenv import load_dotenv
from kafka import KafkaConsumer

load_dotenv()


class KafkaEventConsumer:

    def __init__(self):
        self.consumer = KafkaConsumer(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            security_protocol="SASL_SSL",
            sasl_mechanism=os.getenv(
                "KAFKA_SASL_MECHANISM",
                "SCRAM-SHA-256",
            ),
            sasl_plain_username=os.environ["KAFKA_SASL_USERNAME"],
            sasl_plain_password=os.environ["KAFKA_SASL_PASSWORD"],
            ssl_cafile=os.environ["KAFKA_CA_CERT_PATH"],

            group_id=os.getenv(
                "KAFKA_NOTIFICATION_GROUP_ID",
                "stablebus-notification-consumer",
            ),

            auto_offset_reset="earliest",
            enable_auto_commit=False,
            max_poll_records=1,

            key_deserializer=lambda key: (
                key.decode("utf-8") if key else None
            ),
            value_deserializer=lambda value: json.loads(
                value.decode("utf-8")
            ),
        )

        self.consumer.subscribe(
            [os.environ["KAFKA_BOOKING_TOPIC"]]
        )

    def consume(self, timeout: float = 10.0):
        records = self.consumer.poll(
            timeout_ms=int(timeout * 1000)
        )

        for messages in records.values():
            for message in messages:
                print(
                    f"Event received: topic={message.topic}, "
                    f"partition={message.partition}, "
                    f"offset={message.offset}, "
                    f"key={message.key}"
                )

                return message

        return None

    def commit(self):
        self.consumer.commit()

    def close(self):
        self.consumer.close()
