"""Trigger the vision pipeline as a background job (or inline with ?wait=true)."""
import json
import uuid
from datetime import date
from pathlib import Path

from pydantic import ValidationError
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile

from backend.app.api.deps import get_centre_or_404, require_roles
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.models import Centre, Role, User
from backend.app.schemas.dashboard import JobOut, RunRequest
from backend.app.schemas.upload import ZonesIn
from backend.app.services import pipeline_runner as runner

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])
OPERATORS = (Role.SUPER_ADMIN, Role.MONITORING_OFFICER)


@router.post("/run", response_model=JobOut)
def run_pipeline(body: RunRequest, response: Response, background: BackgroundTasks, wait: bool = False,
                 _: User = Depends(require_roles(*OPERATORS)), db: Store = Depends(get_db)) -> JobOut:
    if body.profile not in ("normal", "lowbw"):
        raise HTTPException(status_code=422, detail="profile must be 'normal' or 'lowbw'")
    if body.centre_id is not None:
        get_centre_or_404(db, body.centre_id)
        centre_ids = [body.centre_id]
    else:
        centre_ids = [c.id for c in db.find(Centre, sort=[("id", 1)], hydrate=False)]
    if not centre_ids:
        raise HTTPException(status_code=422, detail="No centres to process")

    factory = lambda: db  # noqa: E731 - the Store is thread-safe and stateless, so the job can share it
    job_id = runner.jobs.create()
    if wait:
        runner.run_job(job_id, factory, centre_ids, body.profile, body.session_date)
        return JobOut(**runner.jobs.get(job_id))
    background.add_task(runner.run_job, job_id, factory, centre_ids, body.profile, body.session_date)
    response.status_code = 202
    return JobOut(**runner.jobs.get(job_id))


@router.get("/jobs/{job_id}", response_model=JobOut)
def job_status(job_id: str, _: User = Depends(require_roles(*OPERATORS))) -> JobOut:
    job = runner.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(**job)


VIDEO_EXT = (".mp4", ".mov", ".avi", ".mkv", ".webm")
IMAGE_EXT = (".jpg", ".jpeg", ".png")


async def _save_capped(upload: UploadFile, dest: Path, max_bytes: int, what: str) -> None:
    """Stream an upload to disk, refusing anything over the size cap (so a huge file cannot fill the disk)."""
    size = 0
    with dest.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"The {what} is larger than the {max_bytes // (1024 * 1024)} MB limit.")
            out.write(chunk)
    if size == 0:
        raise HTTPException(status_code=422, detail=f"The {what} file is empty.")


@router.post("/upload", response_model=JobOut, status_code=202)
async def upload_and_analyse(
    background: BackgroundTasks,
    centre_id: int = Form(...),
    zones: str = Form("{\"zones\": []}"),
    session_date: date | None = Form(None),
    profile: str = Form("normal"),
    video: UploadFile = File(...),
    reference: UploadFile = File(...),
    _: User = Depends(require_roles(*OPERATORS)),
    db: Store = Depends(get_db),
) -> JobOut:
    """Analyse an uploaded CCTV clip against an uploaded photo of the empty workplace (same camera view)."""
    if profile not in ("normal", "lowbw"):
        raise HTTPException(status_code=422, detail="profile must be 'normal' or 'lowbw'")
    centre = get_centre_or_404(db, centre_id)
    try:
        parsed = ZonesIn.model_validate(json.loads(zones))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Zones are not valid: {exc}") from exc
    v_ext, r_ext = Path(video.filename or "").suffix.lower(), Path(reference.filename or "").suffix.lower()
    if v_ext not in VIDEO_EXT:
        raise HTTPException(status_code=422, detail=f"Video must be one of: {', '.join(VIDEO_EXT)}")
    if r_ext not in IMAGE_EXT:
        raise HTTPException(status_code=422, detail=f"The workplace photo must be one of: {', '.join(IMAGE_EXT)}")

    settings = get_settings()
    work_dir = Path(settings.data_dir) / "uploads" / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        await _save_capped(reference, work_dir / f"reference{r_ext}", settings.max_upload_image_mb * 1024 * 1024, "photo")
        await _save_capped(video, work_dir / f"video{v_ext}", settings.max_upload_video_mb * 1024 * 1024, "video")
    except HTTPException:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    factory = lambda: db  # noqa: E731
    job_id = runner.jobs.create()
    background.add_task(runner.run_upload_job, job_id, factory, centre.id, work_dir, f"video{v_ext}", f"reference{r_ext}",
                        [z.model_dump() for z in parsed.zones], session_date, profile)
    return JobOut(**runner.jobs.get(job_id))
