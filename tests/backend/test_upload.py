"""Upload-and-analyse endpoint: clip + empty-room photo -> observation on the dashboard.

Uses the real SC005 clip and its empty-room clip (a frame of it is the 'photo'). Starlette's TestClient runs the
background task before returning, so the job is finished by the time the POST comes back.
"""
from pathlib import Path

import cv2
import pytest
from fastapi.testclient import TestClient
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.main import app
from scripts.seed import DEMO_PASSWORD, seed

DATA = Path("data")
CLIP, EMPTY = DATA / "videos" / "SC005.mp4", DATA / "real_footage_source" / "SC005_empty_room.mp4"
pytestmark = pytest.mark.skipif(not CLIP.exists() or not EMPTY.exists(), reason="SC005 footage not present")

# zones in the photo's pixels (848x478 frame of the empty-room clip)
ZONES = ('{"zones": [{"item_type": "chair", "box": [235, 280, 95, 115]}, {"item_type": "chair", "box": [375, 195, 75, 140]},'
         '{"item_type": "chair", "box": [485, 270, 150, 208]}, {"item_type": "machine", "box": [150, 205, 100, 70]}]}')


@pytest.fixture()
def client(tmp_path, monkeypatch, store):
    seed(store)
    app.dependency_overrides[get_db] = lambda: store
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def photo(tmp_path):
    cap = cv2.VideoCapture(str(EMPTY))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 120)
    ok, frame = cap.read()
    assert ok
    path = tmp_path / "photo.png"
    cv2.imwrite(str(path), frame)
    return path


def login(client, email):
    r = client.post("/api/auth/login", data={"username": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def post(client, headers, photo, centre_id, zones=ZONES, video_name="clip.mp4", **extra):
    with CLIP.open("rb") as v, photo.open("rb") as p:
        return client.post("/api/pipeline/upload", headers=headers, data={"centre_id": centre_id, "zones": zones, **extra},
                           files={"video": (video_name, v, "video/mp4"), "reference": ("photo.png", p, "image/png")})


def centre_id(client, h, code="SC001"):
    return next(c["id"] for c in client.get("/api/centres", headers=h).json() if c["code"] == code)


def test_upload_creates_an_observation_and_deletes_the_raw_files(client, photo, tmp_path):
    h = login(client, "officer@skillwatch.local")
    cid = centre_id(client, h)
    r = post(client, h, photo, cid)
    assert r.status_code == 202, r.text
    job = client.get(f"/api/pipeline/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["status"] == "done", job
    res = job["results"][0]
    assert res["estimated_count"] == 3
    assert res["items_detected"] == {"chair": 3, "machine": 1}
    assert "workbench" not in res["sanctioned"]  # no zone drawn, so not compared
    assert any("workbench" in n for n in res["notes"])
    assert client.get(f"/api/observations/{res['observation_id']}/frame", headers=h).status_code == 200
    assert not list((tmp_path / "uploads").glob("*/*"))  # the uploaded video and photo are gone
    detail = client.get(f"/api/centres/{cid}/detail", headers=h).json()
    rows = {row["item_type"]: row for row in detail["inventory_compliance"]}
    assert rows["workbench"]["detected"] is None  # shown as not checked, not as 'all missing'
    assert rows["chair"]["detected"] == 3


def test_upload_without_zones_counts_people_only(client, photo):
    h = login(client, "officer@skillwatch.local")
    r = post(client, h, photo, centre_id(client, h), zones='{"zones": []}')
    job = client.get(f"/api/pipeline/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["status"] == "done" and job["results"][0]["estimated_count"] == 3
    assert job["results"][0]["items_missing"] == {}


def test_upload_is_for_officers_and_validates_input(client, photo):
    admin = login(client, "admin.sc001@skillwatch.local")
    assert post(client, admin, photo, 1).status_code == 403
    h = login(client, "officer@skillwatch.local")
    cid = centre_id(client, h)
    assert post(client, h, photo, cid, video_name="clip.exe").status_code == 422
    assert post(client, h, photo, cid, zones="not json").status_code == 422
    assert post(client, h, photo, cid, zones='{"zones": [{"item_type": "chair", "box": [1, 1, 2, 2]}]}').status_code == 422
    assert post(client, h, photo, 99999).status_code == 404


def test_oversized_video_is_refused_and_cleaned_up(client, photo, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_video_mb", 0)
    h = login(client, "officer@skillwatch.local")
    assert post(client, h, photo, centre_id(client, h)).status_code == 413
    assert not list((tmp_path / "uploads").glob("*"))
