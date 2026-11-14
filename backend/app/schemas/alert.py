from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.enums import AlertStatus, AlertType, Severity


class CommentOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    text: str
    created_at: datetime


class AlertOut(BaseModel):
    id: int
    centre_id: int
    centre_code: str
    centre_name: str
    observation_id: int | None
    alert_type: AlertType
    severity: Severity
    status: AlertStatus
    message: str
    created_at: datetime
    updated_at: datetime


class AlertDetail(AlertOut):
    comments: list[CommentOut]


class StatusChange(BaseModel):
    status: AlertStatus
    comment: str | None = Field(default=None, max_length=2000)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
