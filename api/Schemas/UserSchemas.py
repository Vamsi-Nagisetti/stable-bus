from pydantic import BaseModel, ConfigDict, Field



class UserProfileResponse(BaseModel):
    id: int
    mobile_number: str


class SavedPassengerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    age: int = Field(..., ge=1, le=120)
    gender: str = Field(..., min_length=1, max_length=20)


class SavedPassengerUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    age: int = Field(..., ge=1, le=120)
    gender: str = Field(..., min_length=1, max_length=20)
