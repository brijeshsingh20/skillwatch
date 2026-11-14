"""The evaluation tooling itself must be right, or the accuracy report means nothing."""
from scripts.evaluate import make_scenarios, slot_truth, truth_alerts
from scripts.metrics import Confusion, bias, mae, wilson


def test_confusion_counts_and_rates():
    c = Confusion()
    for predicted, actual in [(1, 1), (1, 1), (1, 0), (0, 1), (0, 0), (0, 0), (0, 0)]:
        c.add(bool(predicted), bool(actual))
    assert (c.tp, c.fp, c.fn, c.tn) == (2, 1, 1, 3)
    assert abs(c.precision - 2 / 3) < 1e-9 and abs(c.recall - 2 / 3) < 1e-9 and abs(c.accuracy - 5 / 7) < 1e-9


def test_undefined_rates_are_none_not_errors():
    c = Confusion()
    c.add(False, False)
    assert c.precision is None and c.recall is None and c.f1 is None


def test_wilson_interval_behaviour():
    lo, hi = wilson(19, 19)
    assert 0.8 < lo < 1.0 and hi == 1.0
    lo2, hi2 = wilson(95, 100)
    assert hi2 - lo2 < hi - lo          # more data, narrower interval
    assert wilson(0, 0) is None


def test_mae_and_bias_signs():
    assert mae([-2, 2, 0]) == 4 / 3 and bias([-2, 2, 0]) == 0
    assert bias([1, 1, 1]) == 1 and mae([]) is None


def test_scenarios_are_reproducible_and_varied():
    a, b = make_scenarios(30, 5), make_scenarios(30, 5)
    assert a == b and a != make_scenarios(30, 6)
    assert any(s["camera_profile"] == "poor" for s in a) and any(s["still_fraction"] for s in make_scenarios(60, 5))
    for s in a:
        assert all(s["present"][k] <= s["sanctioned"][k] for k in s["sanctioned"])
        assert s["present"]["machine"] >= s["not_operable"].get("machine", 0)


def test_truth_alerts_and_slot_truth():
    sc = {"camera_profile": "good", "true_count": 8, "claimed_count": 25, "sanctioned": {"chair": 3, "workbench": 1, "machine": 2},
          "present": {"chair": 3, "workbench": 1, "machine": 1}, "not_operable": {"machine": 1}}
    assert truth_alerts(sc) == {"attendance_mismatch", "equipment_missing", "equipment_not_operable"}
    present, operable = slot_truth(sc)
    assert present["machine-1"] and not present["machine-2"] and operable == {"machine-1": False}
