"""The MongoDB data layer: ids, unique indexes, partial updates, embedded lists, filters on enums and dates."""
from datetime import date, datetime, time, timezone

import pytest

from backend.app.db.store import DuplicateKeyError
from backend.app.models import (
    Alert, AlertStatus, AlertType, AttendanceClaim, Batch, Centre, InventoryItem, ItemType, Observation, Role, Severity, User,
)


def make_centre(store, code="C1"):
    return store.add(Centre(code=code, name="n", district="d", state="s", approved_capacity=10,
                            inventory=[InventoryItem(ItemType.CHAIR, 4)]))


def test_ids_are_sequential_per_collection(store):
    a, b = make_centre(store, "A1"), make_centre(store, "B1")
    assert (a.id, b.id) == (1, 2)
    u = store.add(User(email="x@y.z", full_name="x", hashed_password="h", role=Role.SUPER_ADMIN))
    assert u.id == 1  # each collection counts on its own


def test_unique_indexes(store):
    make_centre(store)
    with pytest.raises(DuplicateKeyError):
        make_centre(store)
    store.add(User(email="x@y.z", full_name="x", hashed_password="h", role=Role.SUPER_ADMIN))
    with pytest.raises(DuplicateKeyError):
        store.add(User(email="x@y.z", full_name="y", hashed_password="h", role=Role.SUPER_ADMIN))
    c = make_centre(store, "C2")
    b = store.add(Batch(centre_id=c.id, name="m", start_time=time(9), end_time=time(13), enrolled=1))
    store.add(AttendanceClaim(centre_id=c.id, batch_id=b.id, session_date=date(2026, 11, 12), claimed_count=3))
    with pytest.raises(DuplicateKeyError):  # one claim per batch per day
        store.add(AttendanceClaim(centre_id=c.id, batch_id=b.id, session_date=date(2026, 11, 12), claimed_count=4))


def test_observations_without_ingest_id_do_not_collide(store):
    for _ in range(2):
        store.add(Observation(centre_id=1, session_date=date(2026, 11, 12), estimated_count=1))
    store.add(Observation(centre_id=1, session_date=date(2026, 11, 12), estimated_count=1, ingest_id="e1"))
    with pytest.raises(DuplicateKeyError):
        store.add(Observation(centre_id=1, session_date=date(2026, 11, 12), estimated_count=1, ingest_id="e1"))
    assert store.count(Observation) == 3


def test_filters_sorting_and_roundtrip_of_dates_and_enums(store):
    for day in (10, 11, 12):
        store.add(Observation(centre_id=1, session_date=date(2026, 11, day), estimated_count=day,
                              captured_at=datetime(2026, 11, day, 9, tzinfo=timezone.utc)))
    got = store.find(Observation, {"session_date": {"$gte": date(2026, 11, 11)}}, sort=[("captured_at", -1)])
    assert [o.estimated_count for o in got] == [12, 11]
    assert isinstance(got[0].session_date, date) and got[0].captured_at.tzinfo is not None
    latest = store.one(Observation, {"centre_id": 1}, sort=[("captured_at", -1), ("id", -1)])
    assert latest.estimated_count == 12


def test_partial_update_and_push_do_not_clobber(store):
    a = store.add(Alert(centre_id=1, alert_type=AlertType.LOW_QUALITY, severity=Severity.LOW, message="m"))
    store.push(Alert, a.id, "comments", {"id": 1, "user_id": 1, "text": "hi", "created_at": datetime.now(timezone.utc)})
    store.update(Alert, a.id, {"status": AlertStatus.RESOLVED})
    back = store.get(Alert, a.id)
    assert back.status == AlertStatus.RESOLVED and [c.text for c in back.comments] == ["hi"]
    assert store.count(Alert, {"status": {"$in": [AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]}}) == 0


def test_centre_loads_its_batches_and_inventory(store):
    c = make_centre(store)
    store.add(Batch(centre_id=c.id, name="b2", start_time=time(14), end_time=time(17), enrolled=2))
    store.add(Batch(centre_id=999, name="other", start_time=time(9), end_time=time(10), enrolled=1))
    loaded = store.get(Centre, c.id)
    assert [b.name for b in loaded.batches] == ["b2"] and loaded.batches[0].start_time == time(14)
    assert loaded.inventory[0].item_type == ItemType.CHAIR
    assert store.get(Centre, c.id, hydrate=False).batches == []
    assert store.get(Centre, 12345) is None
