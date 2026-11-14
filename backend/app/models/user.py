import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from backend.app.models._types import Doc, utcnow


class Role(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    CENTRE_ADMIN = "centre_admin"
    MONITORING_OFFICER = "monitoring_officer"


@dataclass(kw_only=True, eq=False)
class User(Doc):
    collection: ClassVar[str] = "users"
    indexes: ClassVar[list] = [([("email", 1)], {"unique": True})]

    email: str
    full_name: str
    hashed_password: str
    role: Role
    centre_id: int | None = None  # set for centre admins: the one centre they may manage
    is_active: bool = True
    created_at: datetime = field(default_factory=utcnow)

    def to_doc(self) -> dict:
        return dict(email=self.email, full_name=self.full_name, hashed_password=self.hashed_password, role=self.role,
                    centre_id=self.centre_id, is_active=self.is_active, created_at=self.created_at)

    @classmethod
    def from_doc(cls, d: dict) -> "User":
        return cls(id=d["_id"], email=d["email"], full_name=d["full_name"], hashed_password=d["hashed_password"],
                   role=Role(d["role"]), centre_id=d.get("centre_id"), is_active=d.get("is_active", True),
                   created_at=d["created_at"])
