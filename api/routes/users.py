
import logging

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.dependencies.auth import get_current_user
from api.Schemas.UserSchemas import (
    UserProfileResponse,
    ContactDetailsRequest,
    ContactDetailsResponse,
)
from Repositories.UserPassengerRepository import UserPassengerRepository


logger = logging.getLogger("stablebus.users")

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
)


def get_user_repository(request: Request):
    return UserPassengerRepository(request.app.state.dynamodb)


@router.get(
    "/me",
    response_model=UserProfileResponse,
)
def get_my_profile(
    current_user=Depends(get_current_user),
):
    return UserProfileResponse(
        id=current_user.id,
        mobile_number=current_user.mobile_number,
    )


@router.put(
    "/contact-details",
    response_model=ContactDetailsResponse,
)
def save_contact_details(
    contact_request: ContactDetailsRequest,
    current_user=Depends(get_current_user),
    repository=Depends(get_user_repository),
):
    try:
        result = repository.upsert_contact_details(
            user_id=str(current_user.id),
            mobile_number=contact_request.mobile_number,
            email=contact_request.email.strip().lower(),
        )

        return ContactDetailsResponse(
            mobile_number=result["mobile_number"],
            email=result["email"],
        )

    except ClientError:
        logger.exception("Failed to save user contact details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save contact details",
        )


@router.get(
    "/contact-details",
    response_model=ContactDetailsResponse,
)
def get_contact_details(
    current_user=Depends(get_current_user),
    repository=Depends(get_user_repository),
):
    try:
        result = repository.get_contact_details(
            user_id=str(current_user.id)
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact details not found",
            )

        return ContactDetailsResponse(
            mobile_number=result["mobile_number"],
            email=result["email"],
        )

    except ClientError:
        logger.exception("Failed to fetch user contact details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch contact details",
        )
