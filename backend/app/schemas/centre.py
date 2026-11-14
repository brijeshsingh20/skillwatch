from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.enums import CameraStatus, ItemType


class InventoryLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_type: ItemType
    quantity: int = Field(ge=0, le=10000)


class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    start_time: time
    end_time: time
    days: str = Field(default="Mon,Tue,Wed,Thu,Fri,Sat", max_length=40)
    enrolled: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def _times_ordered(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class BatchOut(BatchIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CentreCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    district: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    approved_capacity: int = Field(ge=1, le=10000)
    inventory: list[InventoryLine] = []
    batches: list[BatchIn] = []


class CentreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    district: str | None = Field(default=None, min_length=1, max_length=80)
    state: str | None = Field(default=None, min_length=1, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    approved_capacity: int | None = Field(default=None, ge=1, le=10000)


class CentreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    district: str
    state: str
    latitude: float | None
    longitude: float | None
    approved_capacity: int
    camera_status: CameraStatus
    inventory: list[InventoryLine]
    batches: list[BatchOut]


class CentreSummary(BaseModel):
    id: int
    code: str
    name: str
    district: str
    state: str
    latitude: float | None
    longitude: float | None
    camera_status: CameraStatus
    compliance_score: int | None
    open_alerts: int
    last_observed_at: datetime | None
