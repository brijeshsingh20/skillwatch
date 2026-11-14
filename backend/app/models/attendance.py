"""Attendance claimed by a centre for one batch session."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import ClassVar

from backend.app.enums import ClaimSource
from backend.app.models._types import Doc, utcnow


@dataclass(kw_only=True, eq=False)
class AttendanceClaim(Doc):
    collection: ClassVar[str] = "attendance_claims"
    # one claim per batch per day; centre+date lookups are the common read
    indexes: ClassVar[list] = [([("batch_id", 1), ("session_date", 1)], {"unique": True}),
                               ([("centre_id", 1), ("session_date", -1)], {})]

    centre_id: int
    batch_id: int
    session_date: date
    claimed_count: int
    source: ClaimSource = ClaimSource.MANUAL
    submitted_by: int | None = None
    submitted_at: datetime = field(default_factory=utcnow)

    def to_doc(self) -> dict:
        return dict(centre_id=self.centre_id, batch_id=self.batch_id, session_date=self.session_date,
                    claimed_count=self.claimed_count, source=self.source, submitted_by=self.submitted_by,
                    submitted_at=self.submitted_at)

    @classmethod
    def from_doc(cls, d: dict) -> "AttendanceClaim":
        return cls(id=d["_id"], centre_id=d["centre_id"], batch_id=d["batch_id"],
                   session_date=date.fromisoformat(d["session_date"]), claimed_count=d["claimed_count"],
                   source=ClaimSource(d["source"]), submitted_by=d.get("submitted_by"), submitted_at=d["submitted_at"])
