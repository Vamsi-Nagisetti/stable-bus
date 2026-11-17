from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.Schemas.PreRegistrationSchemas import CreatePreRegistrationRequest
from core.database import get_db
from models.PreRegisteredUser import PreRegisteredUser

router = APIRouter(prefix="/api/v1/preregistrations", tags=["Pre-Registrations"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_pre_registration(
    payload: CreatePreRegistrationRequest,
    db: Session = Depends(get_db),
):
    record = PreRegisteredUser(
        name=payload.name,
        mobile=payload.mobile,
        email=payload.email,
        city=payload.city,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This mobile number or email is already registered",
        )
    db.refresh(record)
    return {
        "id": record.id,
        "name": record.name,
        "mobile": record.mobile,
        "email": record.email,
        "city": record.city,
        "created_at": record.created_at.isoformat(),
    }
