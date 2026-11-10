
import logging

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.dependencies.auth import get_current_user
from api.Schemas.UserSchemas import (
    SavedPassengerCreateRequest,
    SavedPassengerUpdateRequest,
)
from Repositories.UserPassengerRepository import UserPassengerRepository


logger = logging.getLogger("stablebus.passengers")

router = APIRouter(
    prefix="/api/v1/users/passengers",
    tags=["Saved Passengers"]
)


def get_passenger_repository(request: Request):
    return UserPassengerRepository(request.app.state.dynamodb)


@router.post("", status_code=status.HTTP_201_CREATED)
def add_passenger(
    passenger_request: SavedPassengerCreateRequest,
    current_user=Depends(get_current_user),
    repository=Depends(get_passenger_repository),
):
    try:
        return repository.add_passenger(
            user_id=str(current_user.id),
            name=passenger_request.name,
            age=passenger_request.age,
            gender=passenger_request.gender,
        )
    except ClientError:
        logger.exception("Failed to save passenger")
        raise HTTPException(
            status_code=500,
            detail="Unable to save passenger"
        )


@router.get("")
def get_passengers(
    current_user=Depends(get_current_user),
    repository=Depends(get_passenger_repository),
):
    try:
        return repository.get_passengers(str(current_user.id))
    except ClientError:
        logger.exception("Failed to fetch saved passengers")
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch saved passengers"
        )


@router.put("/{passenger_id}")
def update_passenger(
    passenger_id: str,
    passenger_request: SavedPassengerUpdateRequest,
    current_user=Depends(get_current_user),
    repository=Depends(get_passenger_repository),
):
    try:
        return repository.update_passenger(
            user_id=str(current_user.id),
            passenger_id=passenger_id,
            name=passenger_request.name,
            age=passenger_request.age,
            gender=passenger_request.gender,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(status_code=404, detail="Passenger not found")

        logger.exception("Failed to update passenger")
        raise HTTPException(status_code=500, detail="Unable to update passenger")


@router.delete("/{passenger_id}")
def delete_passenger(
    passenger_id: str,
    current_user=Depends(get_current_user),
    repository=Depends(get_passenger_repository),
):
    try:
        deleted = repository.delete_passenger(
            user_id=str(current_user.id),
            passenger_id=passenger_id,
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Passenger not found")

        return {"message": "Passenger deleted successfully"}

    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(status_code=404, detail="Passenger not found")

        logger.exception("Failed to delete passenger")
        raise HTTPException(status_code=500, detail="Unable to delete passenger")
