"""Payloads accepted from the low-bandwidth edge agent (counts + one small pixelated thumbnail)."""
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.enums import ItemType

VALID_ITEMS = {t.value for t in ItemType}


class IngestItem(BaseModel):
    ingest_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    kind: Literal["observation", "camera_offline"] = "observation"
    centre_code: str = Field(min_length=2, max_length=20)
    captured_at: datetime
    session_date: date | None = None
    estimated_count: int | None = Field(default=None, ge=0, le=5000)
    items_detected: dict[str, int] = {}
    items_not_operable: dict[str, int] = {}
    confidence: float = Field(default=0.0, ge=0, le=1)
    frame_quality: float = Field(default=1.0, ge=0, le=1)
    low_quality: bool = False
    thumbnail_b64: str | None = Field(default=None, max_length=90_000)
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("captured_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)

    @field_validator("items_detected", "items_not_operable")
    @classmethod
    def _items(cls, v: dict[str, int]) -> dict[str, int]:
        for key, count in v.items():
            if key not in VALID_ITEMS:
                raise ValueError(f"Unknown item type '{key}'")
            if not 0 <= count <= 10000:
                raise ValueError("Item counts must be between 0 and 10000")
        return v

    @model_validator(mode="after")
    def _kind_fields(self):
        if self.kind == "observation" and self.estimated_count is None:
            raise ValueError("estimated_count is required for observations")
        if self.kind == "camera_offline" and not self.reason:
            raise ValueError("reason is required for camera_offline events")
        return self


class IngestBatch(BaseModel):
    observations: list[IngestItem] = Field(min_length=1, max_length=50)


class IngestResult(BaseModel):
    ingest_id: str
    status: Literal["created", "duplicate", "rejected"]
    observation_id: int | None = None
    alerts: int = 0
    error: str | None = None


class IngestResponse(BaseModel):
    results: list[IngestResult]
