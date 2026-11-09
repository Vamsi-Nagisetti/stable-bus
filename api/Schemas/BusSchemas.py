from typing import Any

from pydantic import BaseModel, ConfigDict


class BusCityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cities: list[dict[str, Any]]
    total: int