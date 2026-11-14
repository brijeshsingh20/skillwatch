"""Database connection. MongoDB; the URL and database name come from MONGO_URL / MONGO_DB (see .env.example)."""
from collections.abc import Iterator
from functools import lru_cache

from backend.app.core.config import get_settings
from backend.app.db.store import Store


@lru_cache
def get_store() -> Store:
    from pymongo import MongoClient  # imported here so the rest of the app imports without pymongo (tests)

    s = get_settings()
    client = MongoClient(s.mongo_url, tz_aware=True, serverSelectionTimeoutMS=5000)
    return Store(client[s.mongo_db])


def get_db() -> Iterator[Store]:
    """FastAPI dependency. Kept as a generator so tests can override it the same way as before."""
    yield get_store()
