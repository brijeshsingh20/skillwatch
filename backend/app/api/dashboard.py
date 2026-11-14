"""Dashboard overview KPIs."""
from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.enums import CameraStatus
from backend.app.models import Alert, Centre, Observation, Role, User
from backend.app.schemas.dashboard import Overview
from backend.app.services import dashboard as dash
from backend.app.services.alerts import ACTIVE

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=Overview)
def overview(user: User = Depends(get_current_user), db: Store = Depends(get_db)) -> Overview:
    scope = {"centre_id": user.centre_id} if user.role == Role.CENTRE_ADMIN else {}
    centres = db.find(Centre, {"id": user.centre_id} if scope else {})
    alerts = db.find(Alert, {"status": {"$in": list(ACTIVE)}, **scope})
    scores = [s.compliance_score for s in dash.centre_summaries(db, centres) if s.compliance_score is not None]
    by_sev: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for a in alerts:
        by_sev[a.severity.value] = by_sev.get(a.severity.value, 0) + 1
        by_type[a.alert_type.value] = by_type.get(a.alert_type.value, 0) + 1
    return Overview(
        centres=len(centres), centres_with_open_alerts=len({a.centre_id for a in alerts}), open_alerts=len(alerts),
        open_alerts_by_severity=by_sev, open_alerts_by_type=by_type,
        average_compliance=round(sum(scores) / len(scores), 1) if scores else None,
        observations_total=db.count(Observation, scope),
        cameras_not_online=sum(1 for c in centres if c.camera_status != CameraStatus.ONLINE))
