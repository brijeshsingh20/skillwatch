"""Read-side helpers for the dashboard: latest observation, compliance, timeline, summaries."""
from datetime import date, timedelta

from backend.app.db.store import Store
from backend.app.enums import AlertStatus
from backend.app.models import Alert, AttendanceClaim, Centre, Observation
from backend.app.schemas.centre import CentreSummary
from backend.app.schemas.dashboard import InventoryRow, TimelinePoint
from backend.app.services.alerts import ACTIVE
from backend.app.services.compliance import compliance_score
from backend.app.services.comparison import DetectionSummary, compare


def latest_observation(db: Store, centre_id: int) -> Observation | None:
    return db.one(Observation, {"centre_id": centre_id}, sort=[("captured_at", -1), ("id", -1)])


def sanctioned_of(centre: Centre) -> dict[str, int]:
    return {i.item_type.value: i.quantity for i in centre.inventory}


def checked_types(obs: Observation) -> set[str]:
    """Item types the observation actually looked at: a checked type is either seen (items_detected) or short (items_missing).
    A type in neither was never checked (e.g. an uploaded clip where no zones were drawn for it), so it is not 'missing'."""
    return set(obs.items_detected or {}) | set(obs.items_missing or {})


def score_for(centre: Centre, obs: Observation | None) -> int | None:
    if obs is None:
        return None
    detection = DetectionSummary(obs.estimated_count, dict(obs.items_detected or {}), dict(obs.items_not_operable or {}),
                                 obs.confidence, obs.frame_quality or 1.0, False)
    checked = checked_types(obs)
    sanctioned = {t: q for t, q in sanctioned_of(centre).items() if t in checked}
    return compliance_score(compare(detection, obs.claimed_count, sanctioned))


def open_alert_counts(db: Store) -> dict[int, int]:
    counts: dict[int, int] = {}
    for a in db.find(Alert, {"status": {"$in": list(ACTIVE)}}):
        counts[a.centre_id] = counts.get(a.centre_id, 0) + 1
    return counts


def centre_summaries(db: Store, centres: list[Centre]) -> list[CentreSummary]:
    counts = open_alert_counts(db)
    out = []
    for c in centres:
        obs = latest_observation(db, c.id)
        out.append(CentreSummary(
            id=c.id, code=c.code, name=c.name, district=c.district, state=c.state, latitude=c.latitude,
            longitude=c.longitude, camera_status=c.camera_status, compliance_score=score_for(c, obs),
            open_alerts=counts.get(c.id, 0), last_observed_at=obs.captured_at if obs else None))
    return out


def inventory_rows(centre: Centre, obs: Observation | None) -> list[InventoryRow]:
    rows = []
    for item in sorted(centre.inventory, key=lambda i: i.item_type.value):
        t = item.item_type.value
        if obs is None or t not in checked_types(obs):
            rows.append(InventoryRow(item_type=t, sanctioned=item.quantity, detected=None, missing=None, not_operable=None))
        else:
            rows.append(InventoryRow(item_type=t, sanctioned=item.quantity,
                                     detected=(obs.items_detected or {}).get(t, 0),
                                     missing=(obs.items_missing or {}).get(t, 0),
                                     not_operable=(obs.items_not_operable or {}).get(t, 0)))
    return rows


def timeline(db: Store, centre_id: int, days: int = 14) -> list[TimelinePoint]:
    since = date.today() - timedelta(days=days)
    claims: dict[date, int] = {}
    for c in db.find(AttendanceClaim, {"centre_id": centre_id, "session_date": {"$gte": since}}):
        claims[c.session_date] = claims.get(c.session_date, 0) + c.claimed_count
    estimates: dict[date, int] = {}
    for o in db.find(Observation, {"centre_id": centre_id, "session_date": {"$gte": since}},
                     sort=[("captured_at", 1), ("id", 1)]):
        estimates[o.session_date] = o.estimated_count  # latest observation of the session day wins
    return [TimelinePoint(date=d, claimed=claims.get(d), estimated=estimates.get(d))
            for d in sorted(set(claims) | set(estimates))]


def observation_out(obs: Observation):
    from backend.app.schemas.observation import ObservationOut

    out = ObservationOut.model_validate(obs)
    out.has_frame = bool(obs.frame_ref)
    out.has_media = bool(obs.video_ref or obs.reference_ref)
    return out
