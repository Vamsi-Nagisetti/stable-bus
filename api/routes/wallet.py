from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependencies.auth import get_current_user
from core.database import get_db
from Services.Wallet.WalletService import WalletService, max_redeem_percent

router = APIRouter(prefix="/api/v1", tags=["Wallet & Trips"])


@router.get("/wallet")
def get_wallet(
    brief: bool = Query(default=False, description="Skip trip counts"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Balance (coins + rupee value) and next expiry.

    Completed trips are credited lazily here too, so the user sees new
    coins immediately even if the background worker has not run yet.
    """
    service = WalletService(db)
    if not brief:
        # The heavier credit sweep only runs for the wallet page, never for
        # the small balance chip / payment screen.
        service.credit_completed_trips(
            user_id=str(current_user.id), batch_size=50
        )
    result = service.get_balance(str(current_user.id))
    result["max_redeem_percent"] = int(max_redeem_percent())
    if not brief:
        stats = service.trip_stats(str(current_user.id), days=30)
        result.update(service.lifetime_summary(str(current_user.id)))
        result["trips"] = {
            "total_completed": stats["total_completed_trips"],
            "last_30_days": stats["completed_trips_in_period"],
        }
    return result


@router.get("/wallet/transactions")
def get_wallet_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WalletService(db)
    items = service.get_transactions(
        str(current_user.id), limit=limit + 1, offset=offset
    )
    return {
        "items": items[:limit],
        "has_more": len(items) > limit,
    }


@router.get("/users/me/trips/stats")
def get_trip_stats(
    days: int | None = Query(
        default=None, ge=1, le=3650,
        description="Also return trips completed in the last N days",
    ),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Total completed trips, and completed trips in the last `days` days."""
    return WalletService(db).trip_stats(str(current_user.id), days=days)