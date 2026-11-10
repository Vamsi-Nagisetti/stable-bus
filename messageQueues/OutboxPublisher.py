import logging

from Repositories.OutboxRepository import OutboxRepository
from messageQueues.KafkaEventProducer import KafkaEventProducer

logger = logging.getLogger(__name__)


class OutboxPublisher:

    def __init__(self, session_factory, producer=None):
        self.session_factory = session_factory
        self.producer = producer or KafkaEventProducer()

    def publish_batch(self, batch_size: int = 10) -> int:
        published_count = 0

        for _ in range(batch_size):
            with self.session_factory() as db:
                repository = OutboxRepository(db)

                event = repository.get_next_pending_event()

                if event is None:
                    break

                try:
                    self.producer.publish(
                        topic=self.producer.topic,
                        key=event.aggregate_id,
                        event={
                            "event_id": event.id,
                            "event_type": event.event_type,
                            "aggregate_type": event.aggregate_type,
                            "aggregate_id": event.aggregate_id,
                            "payload": event.payload,
                            "created_at": event.created_at.isoformat(),
                        },
                    )

                    # Mark published only after Kafka acknowledges.
                    repository.mark_published(event)
                    db.commit()

                    published_count += 1

                    logger.info(
                        "Published event_id=%s type=%s",
                        event.id,
                        event.event_type,
                    )

                except Exception as exc:
                    repository.mark_failed(event, str(exc))
                    db.commit()

                    logger.exception(
                        "Failed publishing event_id=%s",
                        event.id,
                    )

        return published_count

    def close(self):
        self.producer.close()