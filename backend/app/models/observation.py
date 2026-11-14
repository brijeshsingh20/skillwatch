"""One analysed observation produced by the vision pipeline (aggregate data only)."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import ClassVar

from backend.app.models._types import Doc, utcnow


@dataclass(kw_only=True, eq=False)
class Observation(Doc):
    collection: ClassVar[str] = "observations"
    # `ingest_id` is only stored when set, so the sparse unique index makes retried edge uploads idempotent
    indexes: ClassVar[list] = [([("centre_id", 1), ("captured_at", -1)], {}),
                               ([("ingest_id", 1)], {"unique": True, "sparse": True})]

    centre_id: int
    batch_id: int | None = None
    captured_at: datetime = field(default_factory=utcnow)
    session_date: date
    estimated_count: int
    claimed_count: int | None = None
    discrepancy_score: float = 0.0
    items_detected: dict = field(default_factory=dict)       # {"chair": 10, ...} apparently present
    items_missing: dict = field(default_factory=dict)        # {"machine": 1, ...} shortfall versus sanctioned inventory
    items_not_operable: dict = field(default_factory=dict)   # present but apparently not operable
    confidence: float = 0.0
    frame_quality: float | None = None
    frame_ref: str | None = None  # relative path to a privacy-blurred, annotated thumbnail (never raw video)
    ingest_id: str | None = None  # client-generated id from the edge agent
    video_ref: str | None = None      # "cloud:..." reference to the uploaded clip; only set if STORE_UPLOADS_IN_CLOUD=true
    reference_ref: str | None = None  # same, for the empty-room photo

    def to_doc(self) -> dict:
        d = dict(centre_id=self.centre_id, batch_id=self.batch_id, captured_at=self.captured_at,
                 session_date=self.session_date, estimated_count=self.estimated_count, claimed_count=self.claimed_count,
                 discrepancy_score=self.discrepancy_score, items_detected=dict(self.items_detected or {}),
                 items_missing=dict(self.items_missing or {}), items_not_operable=dict(self.items_not_operable or {}),
                 confidence=self.confidence, frame_quality=self.frame_quality, frame_ref=self.frame_ref)
        if self.ingest_id is not None:
            d["ingest_id"] = self.ingest_id
        d["video_ref"], d["reference_ref"] = self.video_ref, self.reference_ref
        return d

    @classmethod
    def from_doc(cls, d: dict) -> "Observation":
        return cls(id=d["_id"], centre_id=d["centre_id"], batch_id=d.get("batch_id"), captured_at=d["captured_at"],
                   session_date=date.fromisoformat(d["session_date"]), estimated_count=d["estimated_count"],
                   claimed_count=d.get("claimed_count"), discrepancy_score=d.get("discrepancy_score", 0.0),
                   items_detected=d.get("items_detected", {}), items_missing=d.get("items_missing", {}),
                   items_not_operable=d.get("items_not_operable", {}), confidence=d.get("confidence", 0.0),
                   frame_quality=d.get("frame_quality"), frame_ref=d.get("frame_ref"), ingest_id=d.get("ingest_id"),
                   video_ref=d.get("video_ref"), reference_ref=d.get("reference_ref"))
