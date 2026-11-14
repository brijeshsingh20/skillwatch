from datetime import date

from pydantic import BaseModel

from backend.app.schemas.alert import AlertOut
from backend.app.schemas.centre import CentreOut
from backend.app.schemas.observation import ObservationOut


class Overview(BaseModel):
    centres: int
    centres_with_open_alerts: int
    open_alerts: int
    open_alerts_by_severity: dict[str, int]
    open_alerts_by_type: dict[str, int]
    average_compliance: float | None
    observations_total: int
    cameras_not_online: int


class InventoryRow(BaseModel):
    item_type: str
    sanctioned: int
    detected: int | None
    missing: int | None
    not_operable: int | None


class TimelinePoint(BaseModel):
    date: date
    claimed: int | None
    estimated: int | None


class CentreDetail(BaseModel):
    centre: CentreOut
    compliance_score: int | None
    latest_observation: ObservationOut | None
    inventory_compliance: list[InventoryRow]
    timeline: list[TimelinePoint]
    open_alerts: list[AlertOut]


class JobOut(BaseModel):
    job_id: str
    status: str  # queued | running | done | failed
    results: list[dict] = []
    error: str | None = None


class RunRequest(BaseModel):
    centre_id: int | None = None  # None = every centre
    profile: str = "normal"
    session_date: date | None = None
