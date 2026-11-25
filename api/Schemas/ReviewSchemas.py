from pydantic import BaseModel, ConfigDict, Field


class CreateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
