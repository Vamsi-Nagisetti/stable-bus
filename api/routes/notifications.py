import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.dependencies.auth import get_current_user
from core.database import get_db
from models.PushDevice import PushDevice

logger = logging.getLogger("stablebus.api.notifications")

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Notifications"],
)


class RegisterPushDeviceRequest(BaseModel):
    expo_push_token: str = Field(min_length=20, max_length=255)
    platform: str = Field(pattern="^(android|ios)$")
    device_name: str | None = Field(default=None, max_length=120)


class UnregisterPushDeviceRequest(BaseModel):
    expo_push_token: str = Field(min_length=20, max_length=255)


def _validate_expo_token(token: str) -> None:
    # Expo tokens normally look like ExponentPushToken[...] or ExpoPushToken[...].
    if not (
        token.startswith("ExponentPushToken[")
        or token.startswith("ExpoPushToken[")
    ) or not token.endswith("]"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Expo push token",
        )


@router.post("/devices", status_code=status.HTTP_200_OK)
def register_push_device(
    payload: RegisterPushDeviceRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_expo_token(payload.expo_push_token)
    user_id = str(current_user.id)
    now = datetime.now(timezone.utc)

    device = db.execute(
        select(PushDevice).where(
            PushDevice.expo_push_token == payload.expo_push_token
        )
    ).scalar_one_or_none()

    if device is None:
        device = PushDevice(
            user_id=user_id,
            expo_push_token=payload.expo_push_token,
            platform=payload.platform,
            device_name=payload.device_name,
            is_active=True,
            last_seen_at=now,
        )
        db.add(device)
    else:
        # A token can move to a different account after logout/login.
        device.user_id = user_id
        device.platform = payload.platform
        device.device_name = payload.device_name
        device.is_active = True
        device.last_seen_at = now

    try:
        db.commit()
        db.refresh(device)
    except IntegrityError:
        db.rollback()
        logger.exception("Push device registration conflict")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to register this device",
        )

    return {"success": True, "device_id": device.id}


@router.delete("/devices", status_code=status.HTTP_200_OK)
def unregister_push_device(
    payload: UnregisterPushDeviceRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_expo_token(payload.expo_push_token)
    result = db.execute(
        update(PushDevice)
        .where(
            PushDevice.user_id == str(current_user.id),
            PushDevice.expo_push_token == payload.expo_push_token,
        )
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    db.commit()
    return {"success": True, "deactivated": result.rowcount > 0}
