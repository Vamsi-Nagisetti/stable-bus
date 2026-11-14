
import logging
import time

from core.database import SessionLocal
from messageQueues.OutboxPublisher import OutboxPublisher

logger = logging.getLogger(__name__)


def main():
    publisher = None

    try:
        publisher = OutboxPublisher(
            session_factory=SessionLocal
        )

        logger.info(
            "Outbox publisher worker started"
        )

        while True:
            published_count = publisher.publish_batch(
                batch_size=10
            )

            if published_count == 0:
                time.sleep(2)

    except KeyboardInterrupt:
        logger.info(
            "Outbox publisher worker stopping..."
        )

    except Exception:
        logger.exception(
            "Outbox publisher worker encountered an error"
        )
        raise

    finally:
        if publisher is not None:
            publisher.close()

        logger.info(
            "Outbox publisher worker stopped"
        )


if __name__ == "__main__":
    main()
