"""Training centres: CRUD, sanctioned inventory, batches, detail view."""
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.api.deps import ensure_centre_access, get_centre_or_404, get_current_user, require_roles
from backend.app.db.session import get_db
from backend.app.db.store import DuplicateKeyError, Store
from backend.app.models import (
    Alert, AttendanceClaim, Batch, Centre, InventoryItem, Observation, Role, User,
)
from backend.app.schemas.alert import AlertOut
from backend.app.schemas.attendance import ClaimOut  # noqa: F401  (re-export for API docs grouping)
from backend.app.schemas.centre import (
    BatchIn, BatchOut, CentreCreate, CentreOut, CentreSummary, CentreUpdate, InventoryLine,
)
from backend.app.schemas.dashboard import CentreDetail
from backend.app.schemas.observation import ObservationOut
from backend.app.services import dashboard as dash
from backend.app.services import storage
from backend.app.services.alerts import ACTIVE

router = APIRouter(prefix="/api/centres", tags=["centres"])
SUPER = Depends(require_roles(Role.SUPER_ADMIN))


def _inventory(lines: list[InventoryLine]) -> list[InventoryItem]:
    types = [ln.item_type for ln in lines]
    if len(types) != len(set(types)):
        raise HTTPException(status_code=422, detail="Each item type may appear only once in the inventory")
    return [InventoryItem(ln.item_type, ln.quantity) for ln in lines]


@router.get("", response_model=list[CentreSummary])
def list_centres(user: User = Depends(get_current_user), db: Store = Depends(get_db)) -> list[CentreSummary]:
    flt = {"id": user.centre_id} if user.role == Role.CENTRE_ADMIN else {}
    return dash.centre_summaries(db, db.find(Centre, flt, sort=[("name", 1)]))


@router.post("", response_model=CentreOut, status_code=status.HTTP_201_CREATED, dependencies=[SUPER])
def create_centre(body: CentreCreate, db: Store = Depends(get_db)) -> Centre:
    code = body.code.upper()
    if db.one(Centre, {"code": code}):
        raise HTTPException(status_code=409, detail="Centre code already exists")
    centre = Centre(code=code, name=body.name, district=body.district, state=body.state, latitude=body.latitude,
                    longitude=body.longitude, approved_capacity=body.approved_capacity,
                    inventory=_inventory(body.inventory))
    try:
        db.add(centre)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Centre code already exists")
    for b in body.batches:
        batch = Batch(centre_id=centre.id, **b.model_dump())
        db.add(batch)
        centre.batches.append(batch)
    return centre


@router.get("/{centre_id}", response_model=CentreOut)
def get_centre(centre_id: int, user: User = Depends(get_current_user), db: Store = Depends(get_db)) -> Centre:
    ensure_centre_access(user, centre_id)
    return get_centre_or_404(db, centre_id)


@router.patch("/{centre_id}", response_model=CentreOut, dependencies=[SUPER])
def update_centre(centre_id: int, body: CentreUpdate, db: Store = Depends(get_db)) -> Centre:
    centre = get_centre_or_404(db, centre_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None and key not in ("latitude", "longitude"):
            continue  # required columns can't be cleared
        setattr(centre, key, value)
    db.save(centre)
    return centre


@router.delete("/{centre_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SUPER])
def delete_centre(centre_id: int, db: Store = Depends(get_db)) -> None:
    """Remove the centre and everything that belongs to it. The centre document goes last, so a crash midway leaves
    a centre that can simply be deleted again."""
    centre = get_centre_or_404(db, centre_id)
    db.update_many(User, {"centre_id": centre_id}, {"centre_id": None})
    for obs in db.find(Observation, {"centre_id": centre_id}, hydrate=False):
        storage.delete_cloud_frame(obs.frame_ref)
        storage.delete_cloud_asset(obs.video_ref, "video")
        storage.delete_cloud_asset(obs.reference_ref, "image")
    for model in (Alert, Observation, AttendanceClaim, Batch):
        db.delete(model, {"centre_id": centre_id})
    db.delete(Centre, {"id": centre.id})


@router.put("/{centre_id}/inventory", response_model=CentreOut, dependencies=[SUPER])
def set_inventory(centre_id: int, lines: list[InventoryLine], db: Store = Depends(get_db)) -> Centre:
    """Replace the sanctioned inventory. Super Administrator only, so a centre cannot lower its own bar."""
    centre = get_centre_or_404(db, centre_id)
    centre.inventory = _inventory(lines)
    db.update(Centre, centre.id, {"inventory": [{"item_type": i.item_type, "quantity": i.quantity} for i in centre.inventory]})
    return centre


@router.post("/{centre_id}/batches", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def add_batch(centre_id: int, body: BatchIn, user: User = Depends(require_roles(Role.SUPER_ADMIN, Role.CENTRE_ADMIN)),
              db: Store = Depends(get_db)) -> Batch:
    ensure_centre_access(user, centre_id)
    centre = get_centre_or_404(db, centre_id)
    batch = Batch(centre_id=centre.id, **body.model_dump())
    db.add(batch)
    return batch


@router.delete("/{centre_id}/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(centre_id: int, batch_id: int,
                 user: User = Depends(require_roles(Role.SUPER_ADMIN, Role.CENTRE_ADMIN)),
                 db: Store = Depends(get_db)) -> None:
    ensure_centre_access(user, centre_id)
    batch = db.get(Batch, batch_id)
    if batch is None or batch.centre_id != centre_id:
        raise HTTPException(status_code=404, detail="Batch not found")
    db.delete(AttendanceClaim, {"batch_id": batch_id})
    db.update_many(Observation, {"batch_id": batch_id}, {"batch_id": None})
    db.delete(Batch, {"id": batch_id})


@router.get("/{centre_id}/observations", response_model=list[ObservationOut])
def list_observations(centre_id: int, limit: int = 50, user: User = Depends(get_current_user),
                      db: Store = Depends(get_db)) -> list[ObservationOut]:
    ensure_centre_access(user, centre_id)
    get_centre_or_404(db, centre_id)
    rows = db.find(Observation, {"centre_id": centre_id}, sort=[("captured_at", -1), ("id", -1)], limit=max(1, min(limit, 500)))
    return [dash.observation_out(o) for o in rows]


@router.get("/{centre_id}/detail", response_model=CentreDetail)
def centre_detail(centre_id: int, user: User = Depends(get_current_user), db: Store = Depends(get_db)) -> CentreDetail:
    ensure_centre_access(user, centre_id)
    centre = get_centre_or_404(db, centre_id)
    obs = dash.latest_observation(db, centre_id)
    alerts = db.find(Alert, {"centre_id": centre_id, "status": {"$in": list(ACTIVE)}}, sort=[("created_at", -1)])
    return CentreDetail(
        centre=CentreOut.model_validate(centre), compliance_score=dash.score_for(centre, obs),
        latest_observation=dash.observation_out(obs) if obs else None,
        inventory_compliance=dash.inventory_rows(centre, obs), timeline=dash.timeline(db, centre_id),
        open_alerts=[AlertOut(id=a.id, centre_id=a.centre_id, centre_code=centre.code, centre_name=centre.name,
                              observation_id=a.observation_id, alert_type=a.alert_type, severity=a.severity,
                              status=a.status, message=a.message, created_at=a.created_at, updated_at=a.updated_at)
                    for a in alerts])
