
from datetime import datetime, timezone

from Workers.PaymentReconciliationWorker import (
    PaymentReconciliationWorker,
)


class FakeResult:
    def all(self):
        return []


class FakeDatabase:
    def __init__(self):
        self.statements = []
        self.committed = False
        self.closed = False

    def scalars(self, statement):
        self.statements.append(statement)
        return FakeResult()

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_expire_overdue_records_respects_active_leases():
    database = FakeDatabase()

    worker = PaymentReconciliationWorker(
        payment_provider=None,
        cache=None,
        gateway_name="MOCK",
        session_factory=lambda: database,
    )

    worker._expire_overdue_records()

    assert len(database.statements) == 2
    assert database.committed is True
    assert database.closed is True

    for statement in database.statements:
        sql = str(
            statement.compile(
                compile_kwargs={"literal_binds": True}
            )
        )

        assert "reconciliation_locked_until IS NULL" in sql
        assert "reconciliation_locked_until <=" in sql
