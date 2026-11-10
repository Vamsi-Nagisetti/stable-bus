import logging
import time

from core.database import SessionLocal
from messageQueues.OutboxPublisher import OutboxPublisher


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    publisher = OutboxPublisher(
        session_factory=SessionLocal
    )

    logger.info("StableBus Outbox Publisher started")

    try:
        while True:
            published_count = publisher.publish_batch(
                batch_size=10
            )

            if published_count:
                logger.info(
                    "Published %s outbox events",
                    published_count,
                )

            # Poll every 2 seconds when no events are available.
            if published_count == 0:
                time.sleep(2)

    except KeyboardInterrupt:
        logger.info("Outbox Publisher stopping")

    finally:
        publisher.close()
        logger.info("Outbox Publisher stopped")


if __name__ == "__main__":
    main()