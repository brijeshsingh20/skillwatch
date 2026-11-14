"""Centralised settings, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "skillwatch"
    secret_key: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173"
    first_admin_email: str = "admin@skillwatch.local"
    first_admin_password: str = "Admin@12345"
    log_level: str = "INFO"
    data_dir: str = "data"
    ingest_api_key: str = ""  # empty = edge ingest disabled
    attendance_tolerance_pct: float = 0.15
    attendance_tolerance_min: int = 2
    max_upload_video_mb: int = 300
    max_upload_image_mb: int = 15
    storage_backend: str = "local"  # "local" (data/thumbnails) or "cloudinary" (for hosts with a throw-away disk)
    store_uploads_in_cloud: bool = False  # also keep the uploaded clip + empty-room photo in Cloudinary (needs STORAGE_BACKEND=cloudinary)
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
