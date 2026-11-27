from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies.auth import get_current_user
from core.database import get_db
from Services.Campaign.GoldMileService import GoldMileService

router = APIRouter(prefix="/api/v1/campaign", tags=["Campaign"])


@router.get("/gold-mile")
def gold_mile_progress(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The signed-in user's Gold Mile tier and progress (completed / upcoming trips)."""
    return GoldMileService(db).progress(current_user)