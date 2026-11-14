from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    centre_id: int
    batch_id: int | None
    captured_at: datetime
    session_date: date
    estimated_count: int
    claimed_count: int | None
    discrepancy_score: float
    items_detected: dict[str, int]
    items_missing: dict[str, int]
    items_not_operable: dict[str, int]
    confidence: float
    frame_quality: float | None
    has_frame: bool = False
    has_media: bool = False  # uploaded video/photo kept in the cloud
