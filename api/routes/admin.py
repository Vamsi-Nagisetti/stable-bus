import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies.admin import require_admin
from core.database import SessionLocal, get_db
from models.User import User
from Services.Notifications.PushDispatchService import PushDispatchService
from Services.Wallet.WalletJobs import run_wallet_jobs
from Services.Wallet.WalletService import WalletError, WalletService

logger = logging.getLogger("stablebus.api.admin")

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)

MAX_DIRECT_TARGETS = 5000


class SendNotificationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=500)
    # Extra payload delivered to the app, e.g. {"type": "OFFER", "route": "/offers"}
    data: dict[str, Any] | None = None

    # Targeting - provide exactly one of: user_ids / mobile_numbers / broadcast
    user_ids: list[str] | None = Field(default=None, max_length=MAX_DIRECT_TARGETS)
    mobile_numbers: list[str] | None = Field(default=None, max_length=MAX_DIRECT_TARGETS)
    broadcast: bool = False
    platform: str | None = Field(default=None, pattern="^(android|ios)$")

    @model_validator(mode="after")
    def _one_target(self):
        chosen = sum([
            bool(self.user_ids),
            bool(self.mobile_numbers),
            bool(self.broadcast),
        ])
        if chosen != 1:
            raise ValueError(
                "Provide exactly one of user_ids, mobile_numbers or broadcast=true"
            )
        return self


def _broadcast_job(title, body, data, platform):
    """Runs after the HTTP response (can take a while for many devices)."""
    dispatcher = PushDispatchService()
    with SessionLocal() as db:
        tokens = dispatcher.all_active_tokens(db, platform)
        result = dispatcher.send_to_tokens(db, tokens, title, body, data)
    logger.info("Broadcast finished %s", result.as_dict())


@router.post("/notifications/send")
def send_custom_notification(
    payload: SendNotificationRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Send a custom push notification.

    Examples
      {"title":"Diwali offer","body":"Flat 10% off","broadcast":true}
      {"title":"Hi","body":"Your refund is done","user_ids":["12","57"]}
      {"title":"Hi","body":"...","mobile_numbers":["9876543210"]}
    """
    data = dict(payload.data or {})
    data.setdefault("type", "CUSTOM")
    dispatcher = PushDispatchService()

    if payload.broadcast:
        background.add_task(
            _broadcast_job, payload.title, payload.body, data, payload.platform
        )
        return {"status": "QUEUED", "target": "broadcast"}

    user_ids = payload.user_ids or []
    if payload.mobile_numbers:
        numbers = [m.strip() for m in payload.mobile_numbers]
        users = db.scalars(
            select(User).where(User.mobile_number.in_(numbers))
        ).all()
        user_ids = [str(u.id) for u in users]
        unknown = len(set(numbers)) - len(users)
    else:
        unknown = 0

    tokens = dispatcher.tokens_for_users(db, user_ids, payload.platform)
    result = dispatcher.send_to_tokens(
        db, tokens, payload.title, payload.body, data
    )
    return {
        "status": "SENT",
        "users_matched": len(user_ids),
        "users_without_match": unknown,
        "devices_targeted": len(tokens),
        **result.as_dict(),
    }


class WalletCreditRequest(BaseModel):
    user_id: str
    coins: int = Field(gt=0, le=1_000_000)
    reason: str = Field(min_length=3, max_length=300)
    # Re-sending the same reference never credits twice.
    reference: str = Field(min_length=3, max_length=100)
    notify: bool = True


@router.post("/wallet/credit")
def admin_wallet_credit(
    payload: WalletCreditRequest,
    db: Session = Depends(get_db),
):
    """Manually give coins (promotions / goodwill). Expires on next 1 Jan."""
    try:
        created = WalletService(db).admin_credit(
            payload.user_id, payload.coins, payload.reason, payload.reference
        )
    except WalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if created and payload.notify:
        dispatcher = PushDispatchService()
        tokens = dispatcher.tokens_for_users(db, [payload.user_id])
        dispatcher.send_to_tokens(
            db, tokens, "StableBus coins added",
            f"{payload.coins} coins were added to your wallet.",
            {"type": "WALLET_CREDIT", "route": "/wallet"},
        )
    return {"credited": created, "coins": payload.coins if created else 0}


@router.post("/wallet/run-jobs")
def admin_run_wallet_jobs(request: Request):
    """Run credit / expiry / release jobs now (same as the worker)."""
    return run_wallet_jobs(
        payment_provider=getattr(request.app.state, "payment_provider", None)
    )
