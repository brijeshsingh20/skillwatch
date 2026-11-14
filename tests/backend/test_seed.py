from backend.app.models import AttendanceClaim, Batch, Centre, Role, User
from scripts.scenario import SCENARIO
from scripts.seed import reset_all, seed


def test_seed_creates_scenario(store):
    seed(store)
    assert store.count(Centre) == len(SCENARIO)
    roles = {u.role for u in store.find(User)}
    assert roles == {Role.SUPER_ADMIN, Role.CENTRE_ADMIN, Role.MONITORING_OFFICER}
    nashik = store.one(Centre, {"code": "SC002"})
    claims = store.find(AttendanceClaim, {"centre_id": nashik.id})
    today_claim = max(claims, key=lambda c: c.session_date)
    assert today_claim.claimed_count == 25  # deliberately inflated
    qty = {i.item_type.value: i.quantity for i in nashik.inventory}
    assert qty == {"chair": 25, "workbench": 5, "machine": 2}
    assert len(nashik.batches) == 1  # batches are loaded with the centre


def test_seed_is_idempotent(store):
    seed(store)
    first = store.count(AttendanceClaim)
    seed(store)
    assert store.count(AttendanceClaim) == first
    assert store.count(Centre) == len(SCENARIO)


def test_reset_clears_everything(store):
    seed(store)
    reset_all(store)
    assert store.count(Centre) == 0
    assert store.count(Batch) == 0
    assert store.count(User) == 0


def test_scenario_is_internally_consistent():
    for sc in SCENARIO:
        assert set(sc["present"]) == set(sc["sanctioned"])
        assert all(sc["present"][k] <= sc["sanctioned"][k] for k in sc["present"])
        if sc["true_count"] != sc["claimed_count"]:
            assert "attendance_mismatch" in sc["expected_alerts"]
