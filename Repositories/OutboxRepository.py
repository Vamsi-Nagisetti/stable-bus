
from typing import Any

from models.OutboxEvent import OutboxEvent


class OutboxRepository:
    def __init__(self, db):
        self.db = db

    def create_event(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            status="PENDING",
            attempts=0,
        )

        self.db.add(event)

        # Do not commit here.
        # The caller must commit this event together with
        # the associated business transaction.
        return event
