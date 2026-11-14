"""Alerts raised by rule-based checks, with officer workflow. Comments are embedded in the alert document."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from backend.app.enums import AlertStatus, AlertType, Severity
from backend.app.models._types import Doc, utcnow

__all__ = ["Alert", "AlertComment", "AlertStatus", "AlertType", "Severity"]


@dataclass(eq=False)
class AlertComment:
    id: int
    user_id: int
    text: str
    created_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True, eq=False)
class Alert(Doc):
    collection: ClassVar[str] = "alerts"
    indexes: ClassVar[list] = [([("centre_id", 1), ("status", 1)], {}), ([("created_at", -1)], {})]

    centre_id: int
    observation_id: int | None = None
    alert_type: AlertType
    severity: Severity
    status: AlertStatus = AlertStatus.OPEN
    message: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    comments: list[AlertComment] = field(default_factory=list)

    def to_doc(self) -> dict:
        return dict(centre_id=self.centre_id, observation_id=self.observation_id, alert_type=self.alert_type,
                    severity=self.severity, status=self.status, message=self.message, created_at=self.created_at,
                    updated_at=self.updated_at,
                    comments=[dict(id=c.id, user_id=c.user_id, text=c.text, created_at=c.created_at) for c in self.comments])

    @classmethod
    def from_doc(cls, d: dict) -> "Alert":
        return cls(id=d["_id"], centre_id=d["centre_id"], observation_id=d.get("observation_id"),
                   alert_type=AlertType(d["alert_type"]), severity=Severity(d["severity"]), status=AlertStatus(d["status"]),
                   message=d["message"], created_at=d["created_at"], updated_at=d["updated_at"],
                   comments=[AlertComment(c["id"], c["user_id"], c["text"], c["created_at"]) for c in d.get("comments", [])])
