from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.enums import ClaimSource


class ClaimIn(BaseModel):
    centre_id: int
    batch_id: int
    session_date: date
    claimed_count: int = Field(ge=0, le=5000)


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    centre_id: int
    batch_id: int
    session_date: date
    claimed_count: int
    source: ClaimSource
    submitted_at: datetime


class CsvRowError(BaseModel):
    row: int
    error: str


class CsvResult(BaseModel):
    created: int
    updated: int
    errors: list[CsvRowError]
