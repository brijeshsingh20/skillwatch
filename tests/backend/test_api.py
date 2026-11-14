"""API tests: role scoping, attendance, pipeline job, alerts workflow, frames."""
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.main import app
from scripts.generate_demo_footage import generate_centre
from scripts.scenario import SCENARIO
from scripts.seed import DEMO_PASSWORD, seed


@pytest.fixture(scope="module")
def footage(tmp_path_factory):
    root = tmp_path_factory.mktemp("api_data")
    for sc in SCENARIO:
        generate_centre(sc, root, duration_s=16, fps=8)
    return root


@pytest.fixture()
def client(footage, monkeypatch, store):
    seed(store)
    app.dependency_overrides[get_db] = lambda: store
    monkeypatch.setattr(get_settings(), "data_dir", str(footage))
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(client, email):
    r = client.post("/api/auth/login", data={"username": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


SUPER, OFFICER = "superadmin@skillwatch.local", "officer@skillwatch.local"


def centre_ids(client, h):
    return {c["code"]: c["id"] for c in client.get("/api/centres", headers=h).json()}


def run_all(client):
    h = auth(client, OFFICER)
    r = client.post("/api/pipeline/run?wait=true", json={}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_centre_admin_is_scoped_to_own_centre(client):
    ids = centre_ids(client, auth(client, SUPER))
    h = auth(client, "admin.sc001@skillwatch.local")
    assert [c["code"] for c in client.get("/api/centres", headers=h).json()] == ["SC001"]
    assert client.get(f"/api/centres/{ids['SC001']}", headers=h).status_code == 200
    assert client.get(f"/api/centres/{ids['SC002']}", headers=h).status_code == 403
    assert client.get(f"/api/centres/{ids['SC002']}/detail", headers=h).status_code == 403


def test_only_super_admin_manages_centres_and_inventory(client):
    body = {"code": "x1", "name": "New", "district": "D", "state": "S", "approved_capacity": 20,
            "inventory": [{"item_type": "chair", "quantity": 5}]}
    assert client.post("/api/centres", json=body, headers=auth(client, OFFICER)).status_code == 403
    created = client.post("/api/centres", json=body, headers=auth(client, SUPER))
    assert created.status_code == 201 and created.json()["code"] == "X1"
    assert client.post("/api/centres", json=body, headers=auth(client, SUPER)).status_code == 409
    cid = created.json()["id"]
    dup = [{"item_type": "chair", "quantity": 1}, {"item_type": "chair", "quantity": 2}]
    assert client.put(f"/api/centres/{cid}/inventory", json=dup, headers=auth(client, SUPER)).status_code == 422
    ok = [{"item_type": "chair", "quantity": 9}, {"item_type": "machine", "quantity": 1}]
    r = client.put(f"/api/centres/{cid}/inventory", json=ok, headers=auth(client, SUPER))
    assert {i["item_type"]: i["quantity"] for i in r.json()["inventory"]} == {"chair": 9, "machine": 1}
    assert client.delete(f"/api/centres/{cid}", headers=auth(client, SUPER)).status_code == 204


def test_manual_claim_and_csv_upload(client):
    sup = auth(client, SUPER)
    ids = centre_ids(client, sup)
    h = auth(client, "admin.sc001@skillwatch.local")
    batch_id = client.get(f"/api/centres/{ids['SC001']}", headers=h).json()["batches"][0]["id"]
    claim = {"centre_id": ids["SC001"], "batch_id": batch_id, "session_date": "2026-01-05", "claimed_count": 11}
    assert client.post("/api/attendance", json=claim, headers=h).status_code == 201
    other = dict(claim, centre_id=ids["SC002"])
    assert client.post("/api/attendance", json=other, headers=h).status_code == 403

    csv_text = "session_date,claimed_count\n2026-01-06,12\n2026-01-07,notanumber\n2026-01-05,13\n"
    r = client.post("/api/attendance/csv", data={"centre_id": ids["SC001"]}, headers=h,
                    files={"file": ("a.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    assert r.status_code == 200
    assert r.json()["created"] == 1 and r.json()["updated"] == 1 and len(r.json()["errors"]) == 1


def test_pipeline_flags_faked_attendance_and_missing_equipment(client):
    job = run_all(client)
    assert job["status"] == "done" and len(job["results"]) == 4
    h = auth(client, OFFICER)
    alerts = client.get("/api/alerts", headers=h).json()
    by_centre: dict[str, set[str]] = {}
    for a in alerts:
        by_centre.setdefault(a["centre_code"], set()).add(a["alert_type"])
    assert by_centre.get("SC001") is None                                 # honest centre: clean
    assert by_centre["SC002"] == {"attendance_mismatch"}                  # faked attendance sheet
    assert by_centre["SC003"] == {"equipment_missing"}                    # missing machine
    assert by_centre["SC004"] == {"attendance_mismatch", "equipment_missing", "equipment_not_operable", "low_quality"}
    overview = client.get("/api/dashboard/overview", headers=h).json()
    assert overview["open_alerts"] == len(alerts) == 6 and overview["observations_total"] == 4


def test_centre_detail_and_frame_access(client):
    run_all(client)
    sup = auth(client, SUPER)
    ids = centre_ids(client, sup)
    detail = client.get(f"/api/centres/{ids['SC002']}/detail", headers=sup).json()
    assert detail["latest_observation"]["estimated_count"] in (7, 8, 9)
    assert detail["compliance_score"] < 100
    assert any(p["claimed"] == 25 and p["estimated"] for p in detail["timeline"] if p["date"] == date.today().isoformat())
    obs_id = detail["latest_observation"]["id"]
    img = client.get(f"/api/observations/{obs_id}/frame", headers=sup)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/observations/{obs_id}/frame").status_code == 401
    assert client.get(f"/api/observations/{obs_id}/frame", headers=auth(client, "admin.sc001@skillwatch.local")).status_code == 403


def test_alert_workflow_roles_and_transitions(client):
    run_all(client)
    off = auth(client, OFFICER)
    alert = next(a for a in client.get("/api/alerts?alert_type=attendance_mismatch", headers=off).json()
                 if a["centre_code"] == "SC002")
    path = f"/api/alerts/{alert['id']}/status"
    assert client.patch(path, json={"status": "acknowledged"}, headers=auth(client, "admin.sc002@skillwatch.local")).status_code == 403
    r = client.patch(path, json={"status": "acknowledged", "comment": "Calling the centre head"}, headers=off)
    assert r.status_code == 200 and r.json()["status"] == "acknowledged" and r.json()["comments"][0]["text"].startswith("Calling")
    assert client.patch(path, json={"status": "acknowledged"}, headers=off).status_code == 409
    assert client.patch(path, json={"status": "resolved", "comment": "Sheet corrected"}, headers=off).json()["status"] == "resolved"
    own = client.get("/api/alerts", headers=auth(client, "admin.sc002@skillwatch.local")).json()
    assert all(a["centre_code"] == "SC002" for a in own)


def test_missing_video_raises_camera_offline_alert(client):
    sup = auth(client, SUPER)
    created = client.post("/api/centres", headers=sup, json={"code": "NOVID", "name": "No Video", "district": "D", "state": "S",
                          "approved_capacity": 10, "inventory": [{"item_type": "chair", "quantity": 2}]}).json()
    r = client.post("/api/pipeline/run?wait=true", json={"centre_id": created["id"]}, headers=auth(client, OFFICER))
    assert r.json()["status"] == "failed"
    types = [a["alert_type"] for a in client.get(f"/api/alerts?centre_id={created['id']}", headers=sup).json()]
    assert types == ["camera_offline"]


def test_background_job_completes_and_can_be_polled(client):
    off = auth(client, OFFICER)
    ids = centre_ids(client, off)
    r = client.post("/api/pipeline/run", json={"centre_id": ids["SC002"]}, headers=off)
    assert r.status_code == 202
    job = client.get(f"/api/pipeline/jobs/{r.json()['job_id']}", headers=off).json()
    assert job["status"] in ("queued", "running", "done")  # TestClient may already have finished it


def test_centre_admin_cannot_run_pipeline(client):
    h = auth(client, "admin.sc001@skillwatch.local")
    assert client.post("/api/pipeline/run", json={}, headers=h).status_code == 403


def test_reports_allow_list_and_auth(client):
    assert client.get("/api/reports/accuracy").status_code == 401
    h = auth(client, OFFICER)
    assert client.get("/api/reports/..%2Fsecrets", headers=h).status_code == 404
    assert client.get("/api/reports/unknown", headers=h).status_code == 404
    assert client.get("/api/reports/privacy", headers=h).status_code in (200, 404)  # 404 until docs are written


# ---------------------------------------------------------------- low-bandwidth edge ingest
class ClientTransport:
    """Lets the edge agent talk to the in-process API through TestClient."""

    def __init__(self, client, key="test-key"):
        self.client, self.key = client, key

    def send(self, body):
        r = self.client.post("/api/ingest/batch", content=body,
                             headers={"Content-Type": "application/json", "X-Ingest-Key": self.key})
        return r.status_code, r.json()


@pytest.fixture()
def ingest(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "ingest_api_key", "test-key")
    return client


def test_ingest_disabled_or_wrong_key(client, monkeypatch):
    body = {"observations": [{"ingest_id": "abcdefgh1", "centre_code": "SC001", "captured_at": "2026-11-10T09:00:00Z", "estimated_count": 12}]}
    monkeypatch.setattr(get_settings(), "ingest_api_key", "")
    assert client.post("/api/ingest/batch", json=body, headers={"X-Ingest-Key": "x"}).status_code == 503
    monkeypatch.setattr(get_settings(), "ingest_api_key", "test-key")
    assert client.post("/api/ingest/batch", json=body).status_code == 401
    assert client.post("/api/ingest/batch", json=body, headers={"X-Ingest-Key": "wrong"}).status_code == 401


def test_edge_agent_end_to_end_flags_faked_attendance(ingest, footage, tmp_path):
    from vision.lowbw import EdgeConfig, run_once

    cfg = EdgeConfig("SC002", data_dir=str(footage), queue_path=str(tmp_path / "edge.db"))
    item, report = run_once(cfg, transport=ClientTransport(ingest))
    assert report.sent == 1 and report.remaining == 0
    h = auth(ingest, OFFICER)
    alerts = ingest.get("/api/alerts", headers=h).json()
    assert {(a["centre_code"], a["alert_type"]) for a in alerts} == {("SC002", "attendance_mismatch")}
    detail = ingest.get(f"/api/centres/{centre_ids(ingest, h)['SC002']}/detail", headers=h).json()
    assert detail["latest_observation"]["has_frame"] is True
    img = ingest.get(f"/api/observations/{detail['latest_observation']['id']}/frame", headers=h)
    assert img.status_code == 200 and img.content.startswith(b"\xff\xd8\xff")


def test_ingest_is_idempotent_and_rejects_bad_items(ingest):
    h = {"X-Ingest-Key": "test-key"}
    good = {"ingest_id": "same-id-0001", "centre_code": "SC001", "captured_at": "2026-11-10T09:00:00Z",
            "session_date": date.today().isoformat(), "estimated_count": 12, "items_detected": {"chair": 12}}
    unknown = dict(good, ingest_id="other-id-0002", centre_code="NOPE")
    bad_thumb = dict(good, ingest_id="thumb-id-0003", thumbnail_b64="bm90IGEganBlZw==")  # "not a jpeg"
    r = ingest.post("/api/ingest/batch", json={"observations": [good, good, unknown, bad_thumb]}, headers=h).json()["results"]
    assert [x["status"] for x in r] == ["created", "duplicate", "rejected", "rejected"]
    assert r[2]["error"] == "Unknown centre" and "JPEG" in r[3]["error"]


def test_ingest_camera_offline_event(ingest):
    h = {"X-Ingest-Key": "test-key"}
    ev = {"kind": "camera_offline", "ingest_id": "offline-0001", "centre_code": "SC003",
          "captured_at": "2026-11-10T09:00:00Z", "reason": "stream timeout"}
    assert ingest.post("/api/ingest/batch", json={"observations": [ev]}, headers=h).json()["results"][0]["status"] == "created"
    types = [a["alert_type"] for a in ingest.get("/api/alerts?centre_id=3", headers=auth(ingest, SUPER)).json()]
    assert "camera_offline" in types


def test_ingest_rejects_invalid_schema(ingest):
    h = {"X-Ingest-Key": "test-key"}
    no_count = {"ingest_id": "nocount-0001", "centre_code": "SC001", "captured_at": "2026-11-10T09:00:00Z"}
    assert ingest.post("/api/ingest/batch", json={"observations": [no_count]}, headers=h).status_code == 422
    bad_item = {"ingest_id": "baditem-0001", "centre_code": "SC001", "captured_at": "2026-11-10T09:00:00Z",
                "estimated_count": 3, "items_detected": {"rocket": 1}}
    assert ingest.post("/api/ingest/batch", json={"observations": [bad_item]}, headers=h).status_code == 422
