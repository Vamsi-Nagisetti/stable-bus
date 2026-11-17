
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select

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
        return event

    def get_next_pending_event(self) -> OutboxEvent | None:
        now = datetime.now(timezone.utc)

        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "PENDING",
                OutboxEvent.available_at <= now,
                or_(
                    OutboxEvent.locked_until.is_(None),
                    OutboxEvent.locked_until < now,
                ),
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        return self.db.execute(statement).scalar_one_or_none()

    def mark_published(self, event: OutboxEvent) -> None:
        event.status = "PUBLISHED"
        event.published_at = datetime.now(timezone.utc)
        event.locked_until = None
        event.last_error = None

    def mark_failed(self, event: OutboxEvent, error: str) -> None:
        event.attempts += 1

        delay = min(5 * (2 ** (event.attempts - 1)), 900)

        event.available_at = (
            datetime.now(timezone.utc) + timedelta(seconds=delay)
        )
        event.locked_until = None
        event.last_error = error[:2000]
