"""Runs the vision pipeline for a centre and feeds the result to the comparison engine.

Used by the API (background job) and by scripts/run_demo.py. The vision package is imported lazily so the
API can start, and non-vision tests can run, without OpenCV installed.
"""
import logging
import shutil
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.db.store import Store
from backend.app.models import Centre, Observation
from backend.app.services import alerts as alert_service
from backend.app.services import storage
from backend.app.services.comparison import DetectionSummary

log = logging.getLogger("skillwatch.pipeline")


def to_detection(result) -> DetectionSummary:
    return DetectionSummary(
        estimated_count=result.estimated_count, items_detected=dict(result.items_detected),
        items_not_operable=dict(result.items_not_operable), confidence=result.confidence,
        frame_quality=result.frame_quality, low_quality=result.low_quality, frame_ref=result.frame_ref)


def run_for_centre(db: Store, centre: Centre, *, profile: str = "normal", session_date: date | None = None,
                   captured_at: datetime | None = None, cached_result=None) -> dict:
    """Analyse one centre's clip. Returns a small status dict; never raises for expected video problems."""
    data_dir = Path(get_settings().data_dir)
    base = {"centre_id": centre.id, "centre_code": centre.code}
    session_date = session_date or date.today()  # same clock the seed script uses for claims
    if cached_result is not None:
        result = cached_result
    else:
        try:
            from vision.pipeline import analyse_centre  # lazy import (OpenCV)
            from vision.types import VideoError
        except ImportError as exc:
            log.error("Vision dependencies missing: %s", exc)
            return {**base, "status": "failed", "error": f"Vision dependencies not installed: {exc}"}
        try:
            result = analyse_centre(centre.code, data_dir, profile)
        except (VideoError, FileNotFoundError) as exc:
            alert = alert_service.record_camera_offline(db, centre, str(exc))
            return {**base, "status": "failed", "error": str(exc), "alert_id": alert.id}
        except Exception as exc:  # noqa: BLE001 - a crash in analysis must not kill the worker
            log.exception("Pipeline crashed for %s", centre.code)
            return {**base, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    outcome = alert_service.process_observation(db, centre, to_detection(result), session_date=session_date,
                                                captured_at=captured_at)
    return {**base, "status": "done",
            "observation_id": outcome.observation.id, "estimated_count": outcome.comparison.estimated_count,
            "claimed_count": outcome.comparison.claimed_count, "alert_ids": [a.id for a in outcome.alerts],
            "new_alerts": len(outcome.created), "processing_seconds": result.processing_seconds}


class JobRegistry:
    """In-memory job table (single-process demo; a real deployment would use a queue)."""

    def __init__(self, keep: int = 200):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._keep = keep

    def create(self) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"job_id": job_id, "status": "queued", "results": [], "error": None}
            while len(self._jobs) > self._keep:
                self._jobs.pop(next(iter(self._jobs)))
        return job_id

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


jobs = JobRegistry()


def run_job(job_id: str, factory, centre_ids: list[int], profile: str, session_date: date | None) -> None:
    jobs.update(job_id, status="running")
    results: list[dict] = []
    try:
        with factory() as db:
            for cid in centre_ids:
                centre = db.get(Centre, cid)
                if centre is None:
                    results.append({"centre_id": cid, "status": "failed", "error": "Centre not found"})
                    continue
                results.append(run_for_centre(db, centre, profile=profile, session_date=session_date))
        failed = [r for r in results if r["status"] == "failed"]
        jobs.update(job_id, status="failed" if len(failed) == len(results) else "done", results=results,
                    error=None if not failed else f"{len(failed)} of {len(results)} centres failed")
    except Exception as exc:  # noqa: BLE001
        log.exception("Job %s crashed", job_id)
        jobs.update(job_id, status="failed", results=results, error=f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------------------------------------------------
# Uploaded footage: one clip + one photo of the empty workplace, analysed on demand
# ---------------------------------------------------------------------------------------------------------------------
def run_upload(db: Store, centre: Centre, *, video_path: Path, reference_path: Path, zones: list[dict],
               session_date: date | None = None, profile: str = "normal") -> dict:
    """Analyse an uploaded clip against an uploaded empty-room photo and store the result like any other observation.

    `zones` are boxes drawn on the photo ({"item_type", "box": [x, y, w, h]} in the photo's pixels). Only item types that
    have at least one zone are compared with the centre's sanctioned inventory; the rest are reported as not checked.
    """
    base = {"centre_id": centre.id, "centre_code": centre.code}
    try:
        from vision.config import load_config
        from vision.types import VideoError
        from vision.upload_analysis import analyse_upload
    except ImportError as exc:
        return {**base, "status": "failed", "error": f"Vision dependencies not installed: {exc}"}
    try:
        result, counts = analyse_upload(video_path, reference_path, zones, centre.code, load_config(profile),
                                        Path(get_settings().data_dir) / "thumbnails")
    except VideoError as exc:
        return {**base, "status": "failed", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("Upload analysis crashed for %s", centre.code)
        return {**base, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    outcome = alert_service.process_observation(db, centre, to_detection(result), session_date=session_date or date.today(),
                                                check_types=set(counts))
    comp = outcome.comparison
    notes = list(result.notes)
    stored = False
    if storage.uploads_in_cloud():
        stem = f"{centre.code}_{outcome.observation.id}"
        refs = {"video_ref": storage.persist_upload(video_path, kind="video", name=f"{stem}_video"),
                "reference_ref": storage.persist_upload(reference_path, kind="image", name=f"{stem}_photo")}
        db.update(Observation, outcome.observation.id, refs)
        stored = any(refs.values())
        if not all(refs.values()):
            notes.append("The analysis is saved, but the video or photo could not be stored in the cloud.")
    unchecked = sorted({i.item_type.value for i in centre.inventory} - set(counts))
    if counts and unchecked:
        notes.append("Item types without a zone were not checked: " + ", ".join(unchecked) + ".")
    return {**base, "status": "done", "observation_id": outcome.observation.id, "estimated_count": comp.estimated_count,
            "claimed_count": comp.claimed_count, "items_detected": comp.items_detected, "items_missing": comp.items_missing,
            "sanctioned": comp.sanctioned, "alert_ids": [a.id for a in outcome.alerts], "new_alerts": len(outcome.created),
            "confidence": result.confidence, "notes": notes, "processing_seconds": result.processing_seconds,
            "stored_in_cloud": stored}


def run_upload_job(job_id: str, factory, centre_id: int, work_dir: Path, video_name: str, ref_name: str,
                   zones: list[dict], session_date: date | None, profile: str) -> None:
    """Background wrapper. The uploaded video and photo are deleted afterwards: only the blurred thumbnail and the
    aggregate numbers are kept (same privacy rule as the rest of the system)."""
    jobs.update(job_id, status="running")
    try:
        with factory() as db:
            centre = db.get(Centre, centre_id)
            if centre is None:
                result = {"centre_id": centre_id, "status": "failed", "error": "Centre not found"}
            else:
                result = run_upload(db, centre, video_path=work_dir / video_name, reference_path=work_dir / ref_name,
                                    zones=zones, session_date=session_date, profile=profile)
        jobs.update(job_id, status=result["status"], results=[result], error=result.get("error"))
    except Exception as exc:  # noqa: BLE001
        log.exception("Upload job %s crashed", job_id)
        jobs.update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
