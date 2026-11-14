"""Training centre, its sanctioned inventory (embedded) and its batches/timetable (separate collection)."""
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import ClassVar

from backend.app.enums import CameraStatus, ItemType  # noqa: F401  (re-exported)
from backend.app.models._types import Doc, utcnow


@dataclass(eq=False)
class InventoryItem:
    """One line of the sanctioned inventory. Stored inside the centre document; at most one line per type."""
    item_type: ItemType
    quantity: int


@dataclass(kw_only=True, eq=False)
class Batch(Doc):
    collection: ClassVar[str] = "batches"
    indexes: ClassVar[list] = [([("centre_id", 1)], {})]

    centre_id: int | None = None
    name: str
    start_time: time
    end_time: time
    days: str = "Mon,Tue,Wed,Thu,Fri,Sat"
    enrolled: int

    def to_doc(self) -> dict:
        return dict(centre_id=self.centre_id, name=self.name, start_time=self.start_time.isoformat(),
                    end_time=self.end_time.isoformat(), days=self.days, enrolled=self.enrolled)

    @classmethod
    def from_doc(cls, d: dict) -> "Batch":
        return cls(id=d["_id"], centre_id=d["centre_id"], name=d["name"], start_time=time.fromisoformat(d["start_time"]),
                   end_time=time.fromisoformat(d["end_time"]), days=d["days"], enrolled=d["enrolled"])


@dataclass(kw_only=True, eq=False)
class Centre(Doc):
    collection: ClassVar[str] = "centres"
    indexes: ClassVar[list] = [([("code", 1)], {"unique": True})]

    code: str
    name: str
    district: str
    state: str
    latitude: float | None = None
    longitude: float | None = None
    approved_capacity: int
    camera_status: CameraStatus = CameraStatus.ONLINE
    created_at: datetime = field(default_factory=utcnow)
    inventory: list[InventoryItem] = field(default_factory=list)
    batches: list[Batch] = field(default_factory=list)  # filled in when the centre is loaded; not stored in this document

    def to_doc(self) -> dict:
        return dict(code=self.code, name=self.name, district=self.district, state=self.state, latitude=self.latitude,
                    longitude=self.longitude, approved_capacity=self.approved_capacity, camera_status=self.camera_status,
                    created_at=self.created_at,
                    inventory=[{"item_type": i.item_type, "quantity": i.quantity} for i in self.inventory])

    @classmethod
    def from_doc(cls, d: dict) -> "Centre":
        return cls(id=d["_id"], code=d["code"], name=d["name"], district=d["district"], state=d["state"],
                   latitude=d.get("latitude"), longitude=d.get("longitude"), approved_capacity=d["approved_capacity"],
                   camera_status=CameraStatus(d["camera_status"]), created_at=d["created_at"],
                   inventory=[InventoryItem(ItemType(i["item_type"]), i["quantity"]) for i in d.get("inventory", [])])

    @staticmethod
    def hydrate(store, centre: "Centre") -> None:
        centre.batches = store.find(Batch, {"centre_id": centre.id}, sort=[("id", 1)])
