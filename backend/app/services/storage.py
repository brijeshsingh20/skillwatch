"""Where thumbnails live: the local data folder (default) or Cloudinary (for hosts with a throw-away disk).

The privacy-blurred thumbnail is always sent to the cloud in cloudinary mode. The uploaded video and the empty-room photo
are sent too, but ONLY when STORE_UPLOADS_IN_CLOUD=true (off by default; see docs/PRIVACY.md).

Cloudinary assets use delivery type "authenticated": the URL needs a signature, so the only way to see a thumbnail is
through GET /api/observations/{id}/frame, which checks the login and the centre. The stored reference looks like
"cloud:skillwatch/thumbnails/SC001_2026..."; a plain "thumbnails/x.jpg" is a file in the local data folder.
"""
import logging
from pathlib import Path

import httpx

from backend.app.core.config import get_settings

log = logging.getLogger("skillwatch.storage")
CLOUD_PREFIX = "cloud:"
FOLDER = "skillwatch/thumbnails"
UPLOAD_FOLDER = "skillwatch/uploads"
KINDS = ("image", "video")  # Cloudinary resource types
_uploaded: dict[str, str] = {}  # local frame_ref -> cloud ref

def cloud_enabled() -> bool:
    return get_settings().storage_backend == "cloudinary"


def is_cloud_ref(frame_ref: str | None) -> bool:
    return bool(frame_ref) and frame_ref.startswith(CLOUD_PREFIX)


def validate_config() -> None:
    """Fail at start-up, not on the first upload, if the storage settings are wrong."""
    s = get_settings()
    if s.storage_backend not in ("local", "cloudinary"):
        raise RuntimeError("STORAGE_BACKEND must be 'local' or 'cloudinary'")
    if s.storage_backend == "cloudinary" and not (s.cloudinary_cloud_name and s.cloudinary_api_key and s.cloudinary_api_secret):
        raise RuntimeError("STORAGE_BACKEND=cloudinary needs CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET")
    if s.store_uploads_in_cloud and s.storage_backend != "cloudinary":
        raise RuntimeError("STORE_UPLOADS_IN_CLOUD=true needs STORAGE_BACKEND=cloudinary")


def _sdk():
    import cloudinary  # lazy: local mode (and the tests) do not need the package
    import cloudinary.uploader
    import cloudinary.utils

    s = get_settings()
    cloudinary.config(cloud_name=s.cloudinary_cloud_name, api_key=s.cloudinary_api_key,
                      api_secret=s.cloudinary_api_secret, secure=True)
    return cloudinary


def persist_thumbnail(frame_ref: str | None) -> str | None:
    """Move a freshly written local thumbnail to the cloud and return the reference to store in the database.

    Local mode returns the reference unchanged. If the upload fails, the observation is still saved with the local
    reference (and the problem is logged) so one network error cannot lose the analysis result.
    """
    if not frame_ref or not cloud_enabled() or is_cloud_ref(frame_ref):
        return frame_ref
    if frame_ref in _uploaded:  # already sent: several observations can share one thumbnail file
        return _uploaded[frame_ref]
    path = Path(get_settings().data_dir) / frame_ref
    try:
        cloudinary = _sdk()
        res = cloudinary.uploader.upload(str(path), resource_type="image", type="authenticated",
                                         public_id=f"{FOLDER}/{path.stem}", overwrite=True)
    except Exception:  # noqa: BLE001 - network, credentials and missing-file errors all end the same way
        log.exception("Cloudinary upload failed for %s; keeping the local file", frame_ref)
        return frame_ref
    path.unlink(missing_ok=True)
    _uploaded[frame_ref] = CLOUD_PREFIX + res["public_id"]
    return _uploaded[frame_ref]


def uploads_in_cloud() -> bool:
    return cloud_enabled() and get_settings().store_uploads_in_cloud


def persist_upload(path: Path, *, kind: str, name: str) -> str | None:
    """Send an uploaded video (kind="video") or empty-room photo (kind="image") to Cloudinary. Returns the reference to
    store, or None if the feature is off or the upload failed (the analysis result is never lost because of this)."""
    if not uploads_in_cloud():
        return None
    assert kind in KINDS
    try:
        cloudinary = _sdk()
        opts = dict(resource_type=kind, type="authenticated", public_id=f"{UPLOAD_FOLDER}/{name}", overwrite=True)
        if kind == "video":  # chunked, so a large clip is not sent in one request
            res = cloudinary.uploader.upload_large(str(path), chunk_size=6_000_000, **opts)
        else:
            res = cloudinary.uploader.upload(str(path), **opts)
    except Exception:  # noqa: BLE001
        log.exception("Cloudinary upload of %s failed", name)
        return None
    return CLOUD_PREFIX + res["public_id"]


def signed_url(frame_ref: str, kind: str) -> str:
    """A signed Cloudinary URL for an authenticated asset. Only hand this to a user who passed the login/role check."""
    cloudinary = _sdk()
    url, _ = cloudinary.utils.cloudinary_url(frame_ref[len(CLOUD_PREFIX):], resource_type=kind, type="authenticated",
                                             sign_url=True, secure=True, format="mp4" if kind == "video" else "jpg")
    return url


def fetch_cloud_frame(frame_ref: str) -> bytes | None:
    """Download a stored thumbnail through a signed URL. Returns None if the cloud cannot be reached."""
    url = signed_url(frame_ref, "image")
    try:
        resp = httpx.get(url, timeout=10.0)
    except httpx.HTTPError:
        log.exception("Could not reach Cloudinary for %s", frame_ref)
        return None
    if resp.status_code != 200:
        log.warning("Cloudinary returned %s for %s", resp.status_code, frame_ref)
        return None
    return resp.content


def delete_cloud_asset(ref: str | None, kind: str = "image") -> None:
    """Best effort: remove an asset from the cloud (used when a centre is deleted). Local files are untouched."""
    if not is_cloud_ref(ref) or not cloud_enabled():
        return
    try:
        _sdk().uploader.destroy(ref[len(CLOUD_PREFIX):], resource_type=kind, type="authenticated")
    except Exception:  # noqa: BLE001
        log.exception("Could not delete %s from Cloudinary", ref)


def delete_cloud_frame(frame_ref: str | None) -> None:
    delete_cloud_asset(frame_ref, "image")
