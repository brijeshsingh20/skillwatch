"""Shared fixtures: an isolated database per test.

By default the database is an in-memory stand-in (tests/fake_mongo.py), so the tests need no MongoDB server.
To run the same tests against a real MongoDB, set SKILLWATCH_TEST_MONGO_URL (for example mongodb://localhost:27017):
each test then gets its own throw-away database that is dropped afterwards.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.main import app
from backend.app.models.user import Role, User
from tests.fake_mongo import FakeDatabase


@pytest.fixture()
def store():
    url = os.environ.get("SKILLWATCH_TEST_MONGO_URL")
    if url:
        from pymongo import MongoClient

        client = MongoClient(url, tz_aware=True, serverSelectionTimeoutMS=5000)
        name = f"skillwatch_test_{uuid.uuid4().hex[:10]}"
        s = Store(client[name])
        s.ensure_indexes()
        yield s
        client.drop_database(name)
        client.close()
    else:
        s = Store(FakeDatabase())
        s.ensure_indexes()
        yield s


@pytest.fixture()
def db_session(store):
    for email, role, centre in [
        ("super@t.io", Role.SUPER_ADMIN, None),
        ("centre@t.io", Role.CENTRE_ADMIN, 1),
        ("officer@t.io", Role.MONITORING_OFFICER, None),
    ]:
        store.add(User(email=email, full_name=email, hashed_password=hash_password("Passw0rd!"), role=role, centre_id=centre))
    return store


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    # No lifespan context: the database is already prepared above.
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str = "Passw0rd!") -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
