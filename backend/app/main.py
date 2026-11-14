"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import alerts, attendance, auth, centres, dashboard, ingest, observations, pipeline, reports, users
from backend.app.core.config import get_settings
from backend.app.core.logging import setup_logging
from backend.app.core.security import hash_password
from backend.app.db.session import get_store
from backend.app.models.user import Role, User
from backend.app.services import storage

log = logging.getLogger("skillwatch")


def bootstrap_admin() -> None:
    """Create the first Super Administrator if there are no users yet."""
    s = get_settings()
    db = get_store()
    if db.count(User) == 0:
        db.add(User(email=s.first_admin_email.lower(), full_name="Super Administrator",
                    hashed_password=hash_password(s.first_admin_password), role=Role.SUPER_ADMIN))
        log.info("Created first super admin %s", s.first_admin_email)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    storage.validate_config()
    get_store().ensure_indexes()
    bootstrap_admin()
    yield


app = FastAPI(title="SkillWatch AI", version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(users.router)
for _r in (centres, attendance, pipeline, alerts, observations, dashboard, reports, ingest):
    app.include_router(_r.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
