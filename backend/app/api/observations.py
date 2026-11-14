"""Authenticated access to the privacy-blurred annotated thumbnails."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from backend.app.api.deps import ensure_centre_access, get_current_user, require_roles
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.models import Observation, Role, User
from backend.app.services import storage

router = APIRouter(prefix="/api/observations", tags=["observations"])


@router.get("/{observation_id}/frame")
def observation_frame(observation_id: int, user: User = Depends(get_current_user), db: Store = Depends(get_db)):
    obs = db.get(Observation, observation_id)
    if obs is None or not obs.frame_ref:
        raise HTTPException(status_code=404, detail="No frame for this observation")
    ensure_centre_access(user, obs.centre_id)
    if storage.is_cloud_ref(obs.frame_ref):  # stored in the cloud; the login check above still guards it
        data = storage.fetch_cloud_frame(obs.frame_ref)
        if data is None:
            raise HTTPException(status_code=502, detail="Image storage could not be reached")
        return Response(content=data, media_type="image/jpeg")
    data_dir = Path(get_settings().data_dir).resolve()
    allowed = data_dir / "thumbnails"
    target = (data_dir / obs.frame_ref).resolve()
    if allowed not in target.parents or not target.is_file():  # blocks path tricks and anything outside thumbnails/
        raise HTTPException(status_code=404, detail="Frame file not found")
    return FileResponse(target, media_type="image/jpeg")


@router.get("/{observation_id}/media")
def observation_media(observation_id: int, user: User = Depends(require_roles(Role.SUPER_ADMIN, Role.MONITORING_OFFICER)),
                      db: Store = Depends(get_db)):
    """Signed links to the uploaded video and empty-room photo, if they were kept in the cloud.

    Raw footage is more sensitive than the blurred thumbnail, so only super admins and monitoring officers may open it.
    """
    obs = db.get(Observation, observation_id)
    if obs is None or not (obs.video_ref or obs.reference_ref):
        raise HTTPException(status_code=404, detail="No stored video or photo for this observation")
    ensure_centre_access(user, obs.centre_id)
    return {"video_url": storage.signed_url(obs.video_ref, "video") if obs.video_ref else None,
            "photo_url": storage.signed_url(obs.reference_ref, "image") if obs.reference_ref else None}
