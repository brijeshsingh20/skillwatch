"""Database-backed tests for observation processing and the alert workflow."""
from datetime import date

import pytest
from backend.app.enums import AlertStatus, AlertType, CameraStatus
from backend.app.models import Alert, Centre, Observation, Role, User
from backend.app.services import alerts as svc
from backend.app.services.comparison import DetectionSummary
from scripts.scenario import SCENARIO
from scripts.seed import seed


@pytest.fixture()
def db(store):
    seed(store)
    return store


def detection_for(code: str, low=False):
    sc = next(x for x in SCENARIO if x["code"] == code)
    return DetectionSummary(sc["true_count"], dict(sc["present"]), dict(sc["not_operable"]), 0.9,
                            0.75 if low else 1.0, low, "thumbnails/x.jpg")


def centre(db, code):
    return db.one(Centre, {"code": code})


def test_faked_attendance_creates_high_alert(db):
    out = svc.process_observation(db, centre(db, "SC002"), detection_for("SC002"), session_date=date.today())
    assert out.comparison.claimed_count == 25 and out.observation.estimated_count == 8
    types = {a.alert_type for a in out.alerts}
    assert types == {AlertType.ATTENDANCE_MISMATCH}
    assert out.alerts[0].severity.value == "high"


def test_missing_equipment_creates_alert(db):
    out = svc.process_observation(db, centre(db, "SC003"), detection_for("SC003"), session_date=date.today())
    assert {a.alert_type for a in out.alerts} == {AlertType.EQUIPMENT_MISSING}
    assert out.observation.items_missing == {"machine": 1}


def test_honest_centre_has_no_alerts(db):
    out = svc.process_observation(db, centre(db, "SC001"), detection_for("SC001"), session_date=date.today())
    assert out.alerts == []
    assert centre(db, "SC001").camera_status == CameraStatus.ONLINE


def test_all_four_alert_types_for_worst_centre(db):
    out = svc.process_observation(db, centre(db, "SC004"), detection_for("SC004", low=True), session_date=date.today())
    assert {a.alert_type.value for a in out.alerts} == {
        "attendance_mismatch", "equipment_missing", "equipment_not_operable", "low_quality"}
    assert centre(db, "SC004").camera_status == CameraStatus.LOW_QUALITY


def test_repeat_run_refreshes_instead_of_duplicating(db):
    c = centre(db, "SC002")
    svc.process_observation(db, c, detection_for("SC002"), session_date=date.today())
    out = svc.process_observation(db, c, detection_for("SC002"), session_date=date.today())
    assert out.created == []
    assert db.count(Alert) == 1
    assert db.count(Observation) == 2


def test_status_workflow_and_comments(db):
    out = svc.process_observation(db, centre(db, "SC002"), detection_for("SC002"), session_date=date.today())
    alert = out.alerts[0]
    officer = db.one(User, {"role": Role.MONITORING_OFFICER})
    svc.change_status(db, alert, AlertStatus.ACKNOWLEDGED, officer.id, "Calling the centre head")
    assert alert.status == AlertStatus.ACKNOWLEDGED and len(alert.comments) == 1
    with pytest.raises(ValueError):
        svc.change_status(db, alert, AlertStatus.ACKNOWLEDGED, officer.id)
    svc.change_status(db, alert, AlertStatus.RESOLVED, officer.id, "Sheet corrected")
    assert alert.status == AlertStatus.RESOLVED
    # a resolved alert no longer blocks a fresh one for a new problem
    again = svc.process_observation(db, centre(db, "SC002"), detection_for("SC002"), session_date=date.today())
    assert len(again.created) == 1


def test_camera_offline_alert(db):
    c = centre(db, "SC001")
    alert = svc.record_camera_offline(db, c, "stream timeout")
    assert alert.alert_type == AlertType.CAMERA_OFFLINE and c.camera_status == CameraStatus.OFFLINE


def test_empty_comment_rejected(db):
    out = svc.process_observation(db, centre(db, "SC002"), detection_for("SC002"), session_date=date.today())
    with pytest.raises(ValueError):
        svc.add_comment(db, out.alerts[0], 1, "   ")
