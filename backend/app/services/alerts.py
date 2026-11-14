"""Persist observations and alerts; run the officer workflow (open -> acknowledged -> resolved)."""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from backend.app.core.config import get_settings
from backend.app.db.store import Store
from backend.app.enums import AlertStatus, AlertType, CameraStatus, Severity
from backend.app.models import Alert, AlertComment, AttendanceClaim, Centre, Observation
from backend.app.services import storage
from backend.app.services.comparison import (
    AlertCandidate, Comparison, DetectionSummary, Tolerance, compare, evaluate_rules,
)

log = logging.getLogger("skillwatch.alerts")
ACTIVE = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)
TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
    AlertStatus.OPEN: {AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED},
    AlertStatus.ACKNOWLEDGED: {AlertStatus.RESOLVED, AlertStatus.OPEN},
    AlertStatus.RESOLVED: {AlertStatus.OPEN},  # reopen
}


@dataclass
class Outcome:
    observation: Observation
    comparison: Comparison
    alerts: list[Alert]
    created: list[Alert]


def default_tolerance() -> Tolerance:
    s = get_settings()
    return Tolerance(pct=s.attendance_tolerance_pct, minimum=s.attendance_tolerance_min)


def find_claim(db: Store, centre_id: int, session_date: date, batch_id: int | None = None) -> AttendanceClaim | None:
    flt: dict = {"centre_id": centre_id, "session_date": session_date}
    if batch_id is not None:
        flt["batch_id"] = batch_id
    return db.one(AttendanceClaim, flt, sort=[("submitted_at", -1)])


def upsert_alert(db: Store, centre_id: int, observation_id: int | None, cand: AlertCandidate) -> tuple[Alert, bool]:
    """One unresolved alert per (centre, type): refresh it instead of stacking duplicates."""
    existing = db.one(Alert, {"centre_id": centre_id, "alert_type": cand.alert_type, "status": {"$in": list(ACTIVE)}},
                      sort=[("created_at", -1)])
    if existing is not None:
        fields = dict(observation_id=observation_id, severity=cand.severity, message=cand.message[:500],
                      updated_at=datetime.now(timezone.utc))
        db.update(Alert, existing.id, fields)  # partial update: a comment added meanwhile is not overwritten
        for k, v in fields.items():
            setattr(existing, k, v)
        return existing, False
    alert = Alert(centre_id=centre_id, observation_id=observation_id, alert_type=cand.alert_type,
                  severity=cand.severity, status=AlertStatus.OPEN, message=cand.message[:500])
    db.add(alert)
    return alert, True


def process_observation(db: Store, centre: Centre, detection: DetectionSummary, *, batch_id: int | None = None,
                        session_date: date | None = None, captured_at: datetime | None = None,
                        tolerance: Tolerance | None = None, ingest_id: str | None = None,
                        check_types: set[str] | None = None) -> Outcome:
    """Compare a pipeline result with the centre's claim and inventory, store it, and raise alerts."""
    captured_at = captured_at or datetime.now(timezone.utc)
    session_date = session_date or captured_at.date()
    claim = find_claim(db, centre.id, session_date, batch_id)
    sanctioned = {i.item_type.value: i.quantity for i in centre.inventory}
    if check_types is not None:  # only compare item types that were actually checked (e.g. zones drawn for an upload)
        sanctioned = {t: q for t, q in sanctioned.items() if t in check_types}
    comp = compare(detection, claim.claimed_count if claim else None, sanctioned, tolerance or default_tolerance())

    obs = Observation(
        centre_id=centre.id, batch_id=batch_id or (claim.batch_id if claim else None), captured_at=captured_at, session_date=session_date,
        estimated_count=comp.estimated_count, claimed_count=comp.claimed_count, discrepancy_score=comp.discrepancy_score,
        items_detected=comp.items_detected, items_missing=comp.items_missing, items_not_operable=comp.items_not_operable,
        confidence=detection.confidence, frame_quality=detection.frame_quality, frame_ref=storage.persist_thumbnail(detection.frame_ref), ingest_id=ingest_id,
    )
    db.add(obs)

    alerts, created = [], []
    for cand in evaluate_rules(comp, detection):
        alert, is_new = upsert_alert(db, centre.id, obs.id, cand)
        alerts.append(alert)
        if is_new:
            created.append(alert)

    centre.camera_status = CameraStatus.LOW_QUALITY if detection.low_quality else CameraStatus.ONLINE
    db.update(Centre, centre.id, {"camera_status": centre.camera_status})
    log.info("Centre %s: est=%s claimed=%s alerts=%s", centre.code, comp.estimated_count, comp.claimed_count,
             [a.alert_type.value for a in alerts])
    return Outcome(obs, comp, alerts, created)


def record_camera_offline(db: Store, centre: Centre, reason: str) -> Alert:
    """Called when a feed can't be read at all."""
    centre.camera_status = CameraStatus.OFFLINE
    alert, _ = upsert_alert(db, centre.id, None, AlertCandidate(
        AlertType.CAMERA_OFFLINE, Severity.HIGH, f"No usable video from this centre: {reason}"[:500]))
    db.update(Centre, centre.id, {"camera_status": CameraStatus.OFFLINE})
    return alert


def _new_comment(db: Store, user_id: int, text: str) -> AlertComment:
    return AlertComment(id=db.next_id("alert_comments"), user_id=user_id, text=text.strip(), created_at=datetime.now(timezone.utc))


def _push_comment(db: Store, alert: Alert, comment: AlertComment) -> None:
    db.push(Alert, alert.id, "comments", dict(id=comment.id, user_id=comment.user_id, text=comment.text,
                                              created_at=comment.created_at))
    alert.comments.append(comment)


def change_status(db: Store, alert: Alert, new_status: AlertStatus, user_id: int, comment: str | None = None) -> Alert:
    if new_status == alert.status:
        raise ValueError(f"Alert is already {new_status.value}")
    if new_status not in TRANSITIONS[alert.status]:
        raise ValueError(f"Cannot move an alert from {alert.status.value} to {new_status.value}")
    alert.status = new_status
    alert.updated_at = datetime.now(timezone.utc)
    db.update(Alert, alert.id, {"status": alert.status, "updated_at": alert.updated_at})
    if comment and comment.strip():
        _push_comment(db, alert, _new_comment(db, user_id, comment))
    return alert


def add_comment(db: Store, alert: Alert, user_id: int, text: str) -> AlertComment:
    if not text.strip():
        raise ValueError("Comment cannot be empty")
    comment = _new_comment(db, user_id, text)
    _push_comment(db, alert, comment)
    return comment
