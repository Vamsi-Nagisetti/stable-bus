"""Periodic wallet jobs, shared by the background worker and admin endpoint."""
import logging

from core.database import SessionLocal
from Services.Notifications.PushDispatchService import PushDispatchService
from Services.Wallet.WalletService import WalletService

logger = logging.getLogger("stablebus.wallet.jobs")


def run_wallet_jobs(session_factory=SessionLocal, notify: bool = True) -> dict:
    summary = {"credited_bookings": 0, "credited_coins": 0,
               "expired_coins": 0, "released_coins": 0}

    # 1. credit completed trips (loop until the backlog is drained)
    credited_all: list[dict] = []
    for _ in range(50):
        with session_factory() as db:
            batch = WalletService(db).credit_completed_trips(batch_size=200)
        if not batch:
            break
        credited_all.extend(batch)
    summary["credited_bookings"] = len(credited_all)
    summary["credited_coins"] = sum(c["coins"] for c in credited_all)

    # 2. Jan-1 expiry
    with session_factory() as db:
        service = WalletService(db)
        for _ in range(50):
            expired = service.expire_due_lots()
            summary["expired_coins"] += expired
            if expired == 0:
                break

    # 3. release coins held by dead payments
    with session_factory() as db:
        summary["released_coins"] = WalletService(
            db
        ).release_abandoned_redemptions()

    # 4. tell users about newly earned coins (best effort)
    if notify and credited_all:
        per_user: dict[str, int] = {}
        for item in credited_all:
            per_user[item["user_id"]] = per_user.get(item["user_id"], 0) + item["coins"]
        try:
            dispatcher = PushDispatchService()
            with session_factory() as db:
                for user_id, coins in per_user.items():
                    tokens = dispatcher.tokens_for_users(db, [user_id])
                    if not tokens:
                        continue
                    dispatcher.send_to_tokens(
                        db, tokens,
                        title="You earned StableBus coins!",
                        body=f"{coins} coins were added to your wallet for your completed trip.",
                        data={"type": "WALLET_CREDIT", "route": "/wallet"},
                    )
        except Exception:
            logger.exception("Wallet credit notifications failed")

    return summary
