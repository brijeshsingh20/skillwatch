"""Input shapes for the 'upload footage + empty-room photo' analysis."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_ZONES = 60
MIN_ZONE_PX = 8


class ZoneIn(BaseModel):
    """One piece of equipment drawn on the reference photo, in that photo's own pixel coordinates."""
    item_type: Literal["chair", "workbench", "machine"]
    box: list[int] = Field(min_length=4, max_length=4)  # x, y, width, height

    @field_validator("box")
    @classmethod
    def _box_ok(cls, v: list[int]) -> list[int]:
        x, y, w, h = v
        if x < 0 or y < 0 or w < MIN_ZONE_PX or h < MIN_ZONE_PX:
            raise ValueError(f"each zone must start inside the photo and be at least {MIN_ZONE_PX} px wide and tall")
        return v


class ZonesIn(BaseModel):
    zones: list[ZoneIn] = Field(default_factory=list, max_length=MAX_ZONES)
