"""Document models (plain dataclasses stored in MongoDB by backend.app.db.store.Store)."""
from backend.app.models.alert import Alert, AlertComment, AlertStatus, AlertType, Severity  # noqa: F401
from backend.app.models.attendance import AttendanceClaim, ClaimSource  # noqa: F401
from backend.app.models.centre import Batch, CameraStatus, Centre, InventoryItem, ItemType  # noqa: F401
from backend.app.models.observation import Observation  # noqa: F401
from backend.app.models.user import Role, User  # noqa: F401

ALL_MODELS = [User, Centre, Batch, AttendanceClaim, Observation, Alert]
