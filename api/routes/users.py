
from fastapi import APIRouter, Depends

from api.dependencies.auth import get_current_user
from api.Schemas.UserSchemas import UserProfileResponse


router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
)


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
