
from pydantic import BaseModel


class UserProfileResponse(BaseModel):
    id: int
    mobile_number: str
