"""Real pipeline output -> comparison engine: the flags must match the planted problems."""
import json

import pytest

from backend.app.services.comparison import DetectionSummary, compare, evaluate_rules
from scripts.generate_demo_footage import generate_centre
from scripts.scenario import SCENARIO
from vision.pipeline import analyse_centre


@pytest.fixture(scope="module")
def demo_data(tmp_path_factory):
    root = tmp_path_factory.mktemp("e2e")
    for sc in SCENARIO:
        generate_centre(sc, root, duration_s=24, fps=8)
    return root


@pytest.mark.parametrize("code", [s["code"] for s in SCENARIO])
def test_pipeline_flags_match_expected(demo_data, code):
    sc = next(s for s in SCENARIO if s["code"] == code)
    r = analyse_centre(code, demo_data)
    d = DetectionSummary(r.estimated_count, r.items_detected, r.items_not_operable, r.confidence,
                         r.frame_quality, r.low_quality, r.frame_ref)
    comp = compare(d, sc["claimed_count"], sc["sanctioned"])
    assert sorted(a.alert_type.value for a in evaluate_rules(comp, d)) == sorted(sc["expected_alerts"])
