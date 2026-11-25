
import logging

from Repositories.OutboxRepository import OutboxRepository
from Factories.EventTransportFactory import create_event_transport

logger = logging.getLogger(__name__)


class OutboxPublisher:

    def __init__(self, session_factory, producer=None):
        self.session_factory = session_factory
        self.resources = []

        if producer is None:
            self.producer, self.resources = create_event_transport()
        else:
            # Supports dependency injection in tests.
            self.producer = producer

    def publish_batch(self, batch_size: int = 10) -> int:
        published_count = 0

        for _ in range(batch_size):
            with self.session_factory() as db:
                repository = OutboxRepository(db)

                event = repository.get_next_pending_event()

                if event is None:
                    break

                try:
                    event_data = {
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat(),
                    }

                    self.producer.publish(
                        topic=self.producer.topic,
                        key=event.aggregate_id,
                        event=event_data,
                    )

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
        try:
            self.producer.close()
        except Exception:
            logger.exception("Error closing event producer")

        for resource in self.resources:
            try:
                resource.close()
            except Exception:
                logger.exception(
                    "Error closing event transport resource"
                )
