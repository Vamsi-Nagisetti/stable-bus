
from Workers.PaymentReconciliationWorker import PaymentReconciliationWorker


def test_run_once_processes_claimed_payments_and_refunds(monkeypatch):
    worker = object.__new__(PaymentReconciliationWorker)
    calls = []

    monkeypatch.setattr(
        worker,
        "_claim_batch",
        lambda: ([101, 102], [201, 202]),
    )

    monkeypatch.setattr(
        worker,
        "_process_payment",
        lambda payment_id: calls.append(("payment", payment_id)),
    )

    monkeypatch.setattr(
        worker,
        "_process_refund",
        lambda refund_id: calls.append(("refund", refund_id)),
    )

    monkeypatch.setattr(
        worker,
        "_expire_overdue_records",
        lambda: calls.append(("expire", None)),
    )

    worker.run_once()

    assert calls == [
        ("payment", 101),
        ("payment", 102),
        ("refund", 201),
        ("refund", 202),
        ("expire", None),
    ]


def test_run_once_expires_records_when_no_items_are_claimed(monkeypatch):
    worker = object.__new__(PaymentReconciliationWorker)
    calls = []

    monkeypatch.setattr(worker, "_claim_batch", lambda: ([], []))
    monkeypatch.setattr(
        worker,
        "_expire_overdue_records",
        lambda: calls.append("expire"),
    )

    worker.run_once()

    assert calls == ["expire"]



from datetime import datetime, timedelta


from datetime import datetime, timedelta, timezone


def test_retry_backoff_schedule():
    worker = object.__new__(PaymentReconciliationWorker)

    expected_delays = {
        1: 60,
        2: 300,
        3: 900,
        4: 1800,
        5: 3600,
        6: 10800,
    }

    for attempt, expected_seconds in expected_delays.items():
        before = datetime.now(timezone.utc)
        retry_at = worker._next_retry_at(attempt)
        after = datetime.now(timezone.utc)

        assert before + timedelta(seconds=expected_seconds) <= retry_at
        assert retry_at <= after + timedelta(seconds=expected_seconds)
