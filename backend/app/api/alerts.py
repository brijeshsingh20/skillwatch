"""Alert queue and officer workflow."""
from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.deps import ensure_centre_access, get_current_user, require_roles
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.enums import AlertStatus, AlertType, Severity
from backend.app.models import Alert, Centre, Role, User
from backend.app.schemas.alert import AlertDetail, AlertOut, CommentIn, CommentOut, StatusChange
from backend.app.services import alerts as svc

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
REVIEWERS = (Role.SUPER_ADMIN, Role.MONITORING_OFFICER)


def _out(a: Alert, centre: Centre | None) -> dict:
    return dict(id=a.id, centre_id=a.centre_id, centre_code=centre.code if centre else "?",
                centre_name=centre.name if centre else "Unknown centre", observation_id=a.observation_id,
                alert_type=a.alert_type, severity=a.severity, status=a.status, message=a.message,
                created_at=a.created_at, updated_at=a.updated_at)


def _detail(db: Store, a: Alert) -> AlertDetail:
    comments = []
    for c in sorted(a.comments, key=lambda c: (c.created_at, c.id)):
        author = db.get(User, c.user_id)
        comments.append(CommentOut(id=c.id, user_id=c.user_id, user_name=author.full_name if author else "Unknown",
                                   text=c.text, created_at=c.created_at))
    return AlertDetail(**_out(a, db.get(Centre, a.centre_id, hydrate=False)), comments=comments)


def _load(db: Store, alert_id: int, user: User) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    ensure_centre_access(user, alert.centre_id)
    return alert


@router.get("", response_model=list[AlertOut])
def list_alerts(status: AlertStatus | None = None, severity: Severity | None = None, alert_type: AlertType | None = None,
                centre_id: int | None = None, limit: int = 200, user: User = Depends(get_current_user),
                db: Store = Depends(get_db)) -> list[AlertOut]:
    flt: dict = {}
    if user.role == Role.CENTRE_ADMIN:
        flt["centre_id"] = user.centre_id
    elif centre_id is not None:
        flt["centre_id"] = centre_id
    if status:
        flt["status"] = status
    if severity:
        flt["severity"] = severity
    if alert_type:
        flt["alert_type"] = alert_type
    rows = db.find(Alert, flt, sort=[("created_at", -1), ("id", -1)], limit=max(1, min(limit, 1000)))
    centres = {c.id: c for c in db.find(Centre, hydrate=False)}
    return [AlertOut(**_out(a, centres.get(a.centre_id))) for a in rows]


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: int, user: User = Depends(get_current_user), db: Store = Depends(get_db)) -> AlertDetail:
    return _detail(db, _load(db, alert_id, user))


@router.patch("/{alert_id}/status", response_model=AlertDetail)
def set_status(alert_id: int, body: StatusChange, user: User = Depends(require_roles(*REVIEWERS)),
               db: Store = Depends(get_db)) -> AlertDetail:
    alert = _load(db, alert_id, user)
    try:
        svc.change_status(db, alert, body.status, user.id, body.comment)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _detail(db, _load(db, alert_id, user))


@router.post("/{alert_id}/comments", response_model=AlertDetail, status_code=201)
def add_comment(alert_id: int, body: CommentIn, user: User = Depends(require_roles(*REVIEWERS)),
                db: Store = Depends(get_db)) -> AlertDetail:
    alert = _load(db, alert_id, user)
    try:
        svc.add_comment(db, alert, user.id, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _detail(db, _load(db, alert_id, user))
