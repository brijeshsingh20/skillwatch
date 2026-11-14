"""Attendance claims: manual form, CSV upload, listing."""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from backend.app.api.deps import ensure_centre_access, get_centre_or_404, get_current_user, require_roles
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.enums import ClaimSource
from backend.app.models import AttendanceClaim, Batch, Role, User
from backend.app.schemas.attendance import ClaimIn, ClaimOut, CsvResult, CsvRowError
from backend.app.services.attendance_csv import parse_claims_csv

log = logging.getLogger("skillwatch.attendance")
router = APIRouter(prefix="/api/attendance", tags=["attendance"])
SUBMITTERS = (Role.SUPER_ADMIN, Role.CENTRE_ADMIN)
MAX_CSV_BYTES = 1_000_000


def _upsert(db: Store, centre_id: int, batch_id: int, session_date, count: int, source: ClaimSource,
            user_id: int) -> tuple[AttendanceClaim, bool]:
    claim = db.one(AttendanceClaim, {"batch_id": batch_id, "session_date": session_date})
    if claim:
        claim.claimed_count, claim.source, claim.submitted_by = count, source, user_id
        db.save(claim)
        return claim, False
    claim = AttendanceClaim(centre_id=centre_id, batch_id=batch_id, session_date=session_date, claimed_count=count,
                            source=source, submitted_by=user_id)
    db.add(claim)
    return claim, True


@router.post("", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
def submit_claim(body: ClaimIn, user: User = Depends(require_roles(*SUBMITTERS)), db: Store = Depends(get_db)):
    ensure_centre_access(user, body.centre_id)
    get_centre_or_404(db, body.centre_id)
    batch = db.get(Batch, body.batch_id)
    if batch is None or batch.centre_id != body.centre_id:
        raise HTTPException(status_code=422, detail="Batch does not belong to this centre")
    claim, _ = _upsert(db, body.centre_id, body.batch_id, body.session_date, body.claimed_count, ClaimSource.MANUAL, user.id)
    return claim


@router.post("/csv", response_model=CsvResult)
async def upload_csv(centre_id: int = Form(...), file: UploadFile = File(...),
                     user: User = Depends(require_roles(*SUBMITTERS)), db: Store = Depends(get_db)) -> CsvResult:
    ensure_centre_access(user, centre_id)
    centre = get_centre_or_404(db, centre_id)
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV larger than 1 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")
    batches = {b.id: b.name for b in centre.batches}
    if not batches:
        raise HTTPException(status_code=422, detail="Create a batch for this centre before uploading attendance")
    rows, errors = parse_claims_csv(text, batches)
    created = updated = 0
    for r in rows:
        _, is_new = _upsert(db, centre_id, r.batch_id, r.session_date, r.claimed_count, ClaimSource.CSV, user.id)
        created += is_new
        updated += not is_new
    log.info("CSV for %s: %d created, %d updated, %d errors", centre.code, created, updated, len(errors))
    return CsvResult(created=created, updated=updated, errors=[CsvRowError(row=e.row, error=e.error) for e in errors])


@router.get("", response_model=list[ClaimOut])
def list_claims(centre_id: int, limit: int = 100, user: User = Depends(get_current_user), db: Store = Depends(get_db)):
    ensure_centre_access(user, centre_id)
    get_centre_or_404(db, centre_id)
    return db.find(AttendanceClaim, {"centre_id": centre_id}, sort=[("session_date", -1), ("id", -1)],
                   limit=max(1, min(limit, 500)))
