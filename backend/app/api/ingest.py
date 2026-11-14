"""Edge ingest: accepts batches of compact observations from the low-bandwidth agent.

Auth is a shared secret in the X-Ingest-Key header (INGEST_API_KEY). The server cannot verify that thumbnails
were pixelated at the edge; it only checks that they are small JPEGs. See docs/PRIVACY.md.
"""
import base64
import binascii
import hmac
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.models import Centre, Observation
from backend.app.schemas.ingest import IngestBatch, IngestItem, IngestResponse, IngestResult
from backend.app.services import alerts as alert_service
from backend.app.services.comparison import DetectionSummary

log = logging.getLogger("skillwatch.ingest")
router = APIRouter(prefix="/api/ingest", tags=["ingest"])
MAX_THUMB_BYTES = 60_000
JPEG_MAGIC = b"\xff\xd8\xff"


def require_ingest_key(x_ingest_key: str | None = Header(default=None)) -> None:
    expected = get_settings().ingest_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Edge ingest is disabled: set INGEST_API_KEY")
    if not x_ingest_key or not hmac.compare_digest(x_ingest_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid ingest key")


def _save_thumbnail(item: IngestItem) -> str | None:
    if not item.thumbnail_b64:
        return None
    try:
        raw = base64.b64decode(item.thumbnail_b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("thumbnail is not valid base64")
    if len(raw) > MAX_THUMB_BYTES:
        raise ValueError(f"thumbnail larger than {MAX_THUMB_BYTES // 1000} KB")
    if not raw.startswith(JPEG_MAGIC):
        raise ValueError("thumbnail must be a JPEG")
    folder = Path(get_settings().data_dir) / "thumbnails"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{item.centre_code.upper()}_{item.ingest_id}.jpg"  # server-chosen name: no client-controlled paths
    (folder / name).write_bytes(raw)
    return f"thumbnails/{name}"


def _handle(db: Store, item: IngestItem) -> IngestResult:
    centre = db.one(Centre, {"code": item.centre_code.upper()})
    if centre is None:
        return IngestResult(ingest_id=item.ingest_id, status="rejected", error="Unknown centre")
    if item.kind == "camera_offline":
        alert = alert_service.record_camera_offline(db, centre, item.reason or "unknown")
        return IngestResult(ingest_id=item.ingest_id, status="created", alerts=1 if alert else 0)

    existing = db.one(Observation, {"ingest_id": item.ingest_id})
    if existing is not None:
        return IngestResult(ingest_id=item.ingest_id, status="duplicate", observation_id=existing.id)
    frame_ref = None
    try:
        frame_ref = _save_thumbnail(item)
        detection = DetectionSummary(
            estimated_count=item.estimated_count or 0, items_detected=item.items_detected,
            items_not_operable=item.items_not_operable, confidence=item.confidence, frame_quality=item.frame_quality,
            low_quality=item.low_quality, frame_ref=frame_ref)
        outcome = alert_service.process_observation(
            db, centre, detection, session_date=item.session_date, captured_at=item.captured_at, ingest_id=item.ingest_id)
    except ValueError as exc:
        db.delete(Observation, {"ingest_id": item.ingest_id})  # no transactions: undo a half-stored item so a retry reprocesses it
        return IngestResult(ingest_id=item.ingest_id, status="rejected", error=str(exc))
    except Exception:  # noqa: BLE001 - one bad item must not sink the batch
        db.delete(Observation, {"ingest_id": item.ingest_id})  # undo a half-stored item so a retry reprocesses it
        log.exception("Ingest failed for %s", item.ingest_id)
        if frame_ref:
            (Path(get_settings().data_dir) / frame_ref).unlink(missing_ok=True)
        return IngestResult(ingest_id=item.ingest_id, status="rejected", error="Internal error while storing observation")
    return IngestResult(ingest_id=item.ingest_id, status="created", observation_id=outcome.observation.id,
                        alerts=len(outcome.alerts))


@router.post("/batch", response_model=IngestResponse, dependencies=[Depends(require_ingest_key)])
def ingest_batch(body: IngestBatch, db: Store = Depends(get_db)) -> IngestResponse:
    return IngestResponse(results=[_handle(db, item) for item in body.observations])
