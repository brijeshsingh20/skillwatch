"""Thumbnail storage: local by default, Cloudinary when STORAGE_BACKEND=cloudinary.

Cloudinary is replaced by a small fake module, so these tests need no account, no network and no `cloudinary` package.
"""
import sys
import types
from datetime import date

import httpx
import pytest

from backend.app.core.config import get_settings
from backend.app.models import Centre, Observation
from backend.app.services import storage
from backend.app.services.alerts import process_observation
from backend.app.services.comparison import DetectionSummary
from tests.conftest import login

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes"


class FakeCloud(types.ModuleType):
    """Just enough of the cloudinary package: uploader.upload/destroy and utils.cloudinary_url."""

    def __init__(self):
        super().__init__("cloudinary")
        self.uploads, self.destroyed, self.fail_upload = [], [], False
        self.config = lambda **kw: None
        self.uploader = types.SimpleNamespace(upload=self._upload, destroy=self._destroy)
        self.utils = types.SimpleNamespace(cloudinary_url=self._url)

    def _upload(self, path, **opts):
        if self.fail_upload:
            raise RuntimeError("network down")
        self.uploads.append((path, opts))
        return {"public_id": opts["public_id"]}

    def _destroy(self, public_id, **opts):
        self.destroyed.append((public_id, opts))

    @staticmethod
    def _url(public_id, **opts):
        assert opts["type"] == "authenticated" and opts["sign_url"] is True  # never a public, unsigned URL
        return f"https://res.example/{public_id}.jpg?sig=1", opts


@pytest.fixture()
def cloud(monkeypatch, tmp_path):
    storage._uploaded.clear()
    fake = FakeCloud()
    monkeypatch.setitem(sys.modules, "cloudinary", fake)
    monkeypatch.setitem(sys.modules, "cloudinary.uploader", fake.uploader)
    monkeypatch.setitem(sys.modules, "cloudinary.utils", fake.utils)
    s = get_settings()
    for key, value in (("storage_backend", "cloudinary"), ("cloudinary_cloud_name", "demo"), ("cloudinary_api_key", "k"),
                       ("cloudinary_api_secret", "s"), ("data_dir", str(tmp_path))):
        monkeypatch.setattr(s, key, value)
    (tmp_path / "thumbnails").mkdir()
    return fake


def _thumb(tmp_path, name="SC001_20261112T000000.jpg"):
    path = tmp_path / "thumbnails" / name
    path.write_bytes(JPEG)
    return path, f"thumbnails/{name}"


def test_local_mode_leaves_the_reference_alone(monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_backend", "local")
    assert storage.persist_thumbnail("thumbnails/a.jpg") == "thumbnails/a.jpg"
    assert storage.persist_thumbnail(None) is None


def test_cloud_mode_uploads_as_authenticated_and_removes_the_local_file(cloud, tmp_path):
    path, ref = _thumb(tmp_path)
    stored = storage.persist_thumbnail(ref)
    assert stored == "cloud:skillwatch/thumbnails/SC001_20261112T000000"
    assert cloud.uploads[0][1]["type"] == "authenticated" and cloud.uploads[0][1]["resource_type"] == "image"
    assert not path.exists()
    assert storage.persist_thumbnail(stored) == stored  # already in the cloud: no second upload
    assert len(cloud.uploads) == 1


def test_failed_upload_keeps_the_observation_and_the_local_file(cloud, tmp_path):
    cloud.fail_upload = True
    path, ref = _thumb(tmp_path)
    assert storage.persist_thumbnail(ref) == ref and path.exists()


def test_bad_storage_settings_are_rejected_at_start_up(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "storage_backend", "cloudinary")
    monkeypatch.setattr(s, "cloudinary_api_secret", "")
    with pytest.raises(RuntimeError, match="CLOUDINARY_API_SECRET"):
        storage.validate_config()
    monkeypatch.setattr(s, "storage_backend", "ftp")
    with pytest.raises(RuntimeError, match="STORAGE_BACKEND"):
        storage.validate_config()


def _observation_in_cloud(db, tmp_path):
    centre = Centre(code="SC001", name="Test", district="D", state="S", approved_capacity=20)
    db.add(centre)
    _, ref = _thumb(tmp_path)
    det = DetectionSummary(5, {}, {}, 0.9, 0.9, False, ref)
    return centre, process_observation(db, centre, det, session_date=date.today()).observation


def test_frame_endpoint_serves_cloud_images_only_to_logged_in_users(client, db_session, cloud, tmp_path, monkeypatch):
    centre, obs = _observation_in_cloud(db_session, tmp_path)
    assert obs.frame_ref.startswith("cloud:")
    seen = []
    monkeypatch.setattr(storage.httpx, "get", lambda url, timeout: seen.append(url) or httpx.Response(200, content=JPEG))
    url = f"/api/observations/{obs.id}/frame"
    assert client.get(url).status_code == 401
    ok = client.get(url, headers=login(client, "super@t.io"))
    assert ok.status_code == 200 and ok.content == JPEG and ok.headers["content-type"] == "image/jpeg"
    assert seen and "sig=" in seen[0]


def test_frame_endpoint_reports_unreachable_storage(client, db_session, cloud, tmp_path, monkeypatch):
    _, obs = _observation_in_cloud(db_session, tmp_path)
    monkeypatch.setattr(storage.httpx, "get", lambda url, timeout: httpx.Response(404))
    assert client.get(f"/api/observations/{obs.id}/frame", headers=login(client, "super@t.io")).status_code == 502


def test_deleting_a_centre_removes_its_cloud_thumbnails(client, db_session, cloud, tmp_path):
    centre, obs = _observation_in_cloud(db_session, tmp_path)
    assert client.delete(f"/api/centres/{centre.id}", headers=login(client, "super@t.io")).status_code == 204
    assert [d[0] for d in cloud.destroyed] == [obs.frame_ref[len("cloud:"):]]
    assert db_session.count(Observation, {"centre_id": centre.id}) == 0


# ---- uploaded video / photo kept in the cloud (opt-in) ----

def _enable_uploads(monkeypatch, fake):
    fake.uploader.upload_large = lambda path, **opts: fake._upload(path, **opts)
    monkeypatch.setattr(get_settings(), "store_uploads_in_cloud", True)


def test_uploads_stay_local_unless_the_switch_is_on(cloud, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    assert storage.persist_upload(clip, kind="video", name="v") is None and cloud.uploads == []


def test_video_and_photo_are_uploaded_as_authenticated_assets(cloud, tmp_path, monkeypatch):
    _enable_uploads(monkeypatch, cloud)
    clip, photo = tmp_path / "clip.mp4", tmp_path / "room.jpg"
    clip.write_bytes(b"x"), photo.write_bytes(b"x")
    assert storage.persist_upload(clip, kind="video", name="SC001_7_video") == "cloud:skillwatch/uploads/SC001_7_video"
    assert storage.persist_upload(photo, kind="image", name="SC001_7_photo") == "cloud:skillwatch/uploads/SC001_7_photo"
    assert [o["resource_type"] for _, o in cloud.uploads] == ["video", "image"]
    assert all(o["type"] == "authenticated" for _, o in cloud.uploads)
    cloud.fail_upload = True
    assert storage.persist_upload(clip, kind="video", name="again") is None  # a failure never raises


def test_uploads_switch_requires_the_cloudinary_backend(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "storage_backend", "local")
    monkeypatch.setattr(s, "store_uploads_in_cloud", True)
    with pytest.raises(RuntimeError, match="STORE_UPLOADS_IN_CLOUD"):
        storage.validate_config()


def test_media_endpoint_is_for_officers_and_admins_only(client, db_session, cloud, tmp_path):
    centre, obs = _observation_in_cloud(db_session, tmp_path)
    db_session.update(Observation, obs.id, {"video_ref": "cloud:skillwatch/uploads/v", "reference_ref": "cloud:skillwatch/uploads/p"})
    url = f"/api/observations/{obs.id}/media"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=login(client, "centre@t.io")).status_code == 403  # raw footage: not for centre admins
    body = client.get(url, headers=login(client, "officer@t.io")).json()
    assert "skillwatch/uploads/v" in body["video_url"] and "sig=" in body["video_url"]
    assert "skillwatch/uploads/p" in body["photo_url"]
