"""Pure-logic tests: comparison engine, alert rules, compliance score (no database)."""
import json

import pytest

from backend.app.enums import AlertType, Severity
from backend.app.services.compliance import compliance_score
from backend.app.services.comparison import DetectionSummary, Tolerance, compare, evaluate_rules
from scripts.scenario import SCENARIO


def det(est, detected, not_op=None, quality=1.0, low=False):
    return DetectionSummary(est, detected, not_op or {}, 0.95, quality, low)


def alerts_for(sc, **kw):
    d = det(kw.get("est", sc["true_count"]), sc["present"], sc["not_operable"],
            kw.get("quality", 0.75 if sc["camera_profile"] == "poor" else 1.0), sc["camera_profile"] == "poor")
    comp = compare(d, sc["claimed_count"], sc["sanctioned"])
    return comp, {a.alert_type.value: a for a in evaluate_rules(comp, d)}


def test_inflated_claim_is_high_severity():
    sc = next(s for s in SCENARIO if s["code"] == "SC002")
    comp, alerts = alerts_for(sc)
    assert comp.attendance_mismatch and comp.difference == -17
    assert alerts["attendance_mismatch"].severity is Severity.HIGH
    assert "inflated" in alerts["attendance_mismatch"].message


def test_small_gap_within_tolerance_is_not_flagged():
    comp = compare(det(13, {}), 12, {})
    assert not comp.attendance_mismatch and comp.discrepancy_score == 0.0


def test_absolute_tolerance_floor_protects_small_classes():
    assert not compare(det(7, {}), 5, {}).attendance_mismatch      # gap 2 == floor
    assert compare(det(8, {}), 5, {}).attendance_mismatch          # gap 3 > floor


def test_tolerance_is_configurable():
    tight = Tolerance(pct=0.0, minimum=0)
    assert compare(det(11, {}), 12, {}, tight).attendance_mismatch


def test_under_reporting_is_flagged_with_different_wording():
    comp = compare(det(20, {}), 10, {})
    msg = evaluate_rules(comp, det(20, {}))[0].message
    assert "under-reporting" in msg


def test_no_claim_means_no_attendance_alert():
    comp = compare(det(10, {}), None, {})
    assert comp.claimed_count is None and not comp.attendance_mismatch
    assert evaluate_rules(comp, det(10, {})) == []


def test_missing_machine_flagged_high():
    sc = next(s for s in SCENARIO if s["code"] == "SC003")
    comp, alerts = alerts_for(sc)
    assert comp.items_missing == {"machine": 1}
    assert alerts["equipment_missing"].severity is Severity.HIGH
    assert "attendance_mismatch" not in alerts


def test_low_quality_caps_attendance_severity_and_adds_alert():
    d = det(5, {}, quality=0.4, low=True)
    comp = compare(d, 25, {})
    by = {a.alert_type: a for a in evaluate_rules(comp, d)}
    assert by[AlertType.ATTENDANCE_MISMATCH].severity is Severity.MEDIUM
    assert by[AlertType.LOW_QUALITY].severity is Severity.MEDIUM


@pytest.mark.parametrize("code", [s["code"] for s in SCENARIO])
def test_rules_reproduce_scenario_expectations(code):
    sc = next(s for s in SCENARIO if s["code"] == code)
    _, alerts = alerts_for(sc)
    assert sorted(alerts) == sorted(sc["expected_alerts"])


def test_compliance_scores_rank_centres_sensibly():
    scores = {}
    for sc in SCENARIO:
        comp, _ = alerts_for(sc)
        scores[sc["code"]] = compliance_score(comp)
    assert scores["SC001"] == 100
    assert scores["SC001"] > max(scores["SC002"], scores["SC003"], scores["SC004"])
    assert scores["SC003"] < 95 and scores["SC002"] < 80 and scores["SC004"] < 80
