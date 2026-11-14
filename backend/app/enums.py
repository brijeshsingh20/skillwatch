"""Dependency-free enums shared by models, services and tests."""
import enum


class ItemType(str, enum.Enum):
    CHAIR = "chair"
    WORKBENCH = "workbench"
    MACHINE = "machine"


class CameraStatus(str, enum.Enum):
    ONLINE = "online"
    LOW_QUALITY = "low_quality"
    OFFLINE = "offline"


class ClaimSource(str, enum.Enum):
    MANUAL = "manual"
    CSV = "csv"
    SEED = "seed"


class AlertType(str, enum.Enum):
    ATTENDANCE_MISMATCH = "attendance_mismatch"
    EQUIPMENT_MISSING = "equipment_missing"
    EQUIPMENT_NOT_OPERABLE = "equipment_not_operable"
    CAMERA_OFFLINE = "camera_offline"
    LOW_QUALITY = "low_quality"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
