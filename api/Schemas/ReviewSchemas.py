from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip()[:30] for t in value if isinstance(t, str) and t.strip()]
        return list(dict.fromkeys(cleaned))


class ReviewStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_ids: list[str] = Field(default_factory=list, max_length=100)


class RewardUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coins: int = Field(..., ge=0, le=100000)