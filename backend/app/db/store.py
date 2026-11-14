"""MongoDB data layer.

`Store` wraps a pymongo Database and speaks in model objects (see backend/app/models). Only a small, basic part of the
MongoDB API is used on purpose (insert, find, replace, $set, $push, $inc, delete, count, indexes), so the same code
runs on a real MongoDB and on the in-memory stand-in used by the tests (tests/fake_mongo.py).

* Ids are small integers (a counter per collection) so URLs, JWT subjects and the frontend stay unchanged.
* Writes are immediate: there is no session and no commit. Call `add` to insert, `save` to replace a whole document,
  `update` for a partial change, `push` to append to an embedded list.
* Dates are stored as ISO strings ("2026-11-12"), times as "HH:MM:SS", enums as their string values, so filters and
  sorting on them behave the same in every MongoDB version.
* No multi-document transactions (they need a replica set): an operation that writes several documents can leave
  partial results if it crashes midway. The write order is chosen so that a partial result is harmless.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from enum import Enum
from typing import Any

try:  # pymongo is only needed when talking to a real database
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError
except ImportError:  # pragma: no cover - exercised only where pymongo is not installed
    class DuplicateKeyError(Exception):  # type: ignore[no-redef]
        pass

    class ReturnDocument:  # type: ignore[no-redef]
        AFTER = True

log = logging.getLogger("skillwatch.db")


def encode(value: Any) -> Any:
    """Convert Python values to what is stored in MongoDB (also used on query filters)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [encode(v) for v in value]
    return value


def _flt(flt: dict | None) -> dict:
    out = {}
    for key, value in (flt or {}).items():
        out["_id" if key == "id" else key] = encode(value)
    return out


def _sort(sort: list[tuple[str, int]] | None) -> list[tuple[str, int]]:
    return [("_id" if k == "id" else k, d) for k, d in (sort or [])]


class Store:
    def __init__(self, database):
        self.database = database

    # A Store can stand in where code used `with SessionLocal() as db:` / `with factory() as db:`.
    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def _coll(self, model):
        return self.database[model.collection]

    # ---- ids ---------------------------------------------------------------------------------------------------
    def next_id(self, name: str) -> int:
        doc = self.database["_counters"].find_one_and_update(
            {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
        return int(doc["seq"])

    # ---- reads -------------------------------------------------------------------------------------------------
    def _load(self, model, doc: dict | None, hydrate: bool = True):
        if doc is None:
            return None
        obj = model.from_doc(doc)
        if hydrate and hasattr(model, "hydrate"):
            model.hydrate(self, obj)
        return obj

    def get(self, model, obj_id: int | None, hydrate: bool = True):
        if obj_id is None:
            return None
        return self._load(model, self._coll(model).find_one({"_id": obj_id}), hydrate)

    def one(self, model, flt: dict | None = None, sort: list[tuple[str, int]] | None = None, hydrate: bool = True):
        rows = self.find(model, flt, sort, limit=1, hydrate=hydrate)
        return rows[0] if rows else None

    def find(self, model, flt: dict | None = None, sort: list[tuple[str, int]] | None = None, limit: int = 0,
             hydrate: bool = True) -> list:
        cursor = self._coll(model).find(_flt(flt))
        if sort:
            cursor = cursor.sort(_sort(sort))
        if limit:
            cursor = cursor.limit(limit)
        return [self._load(model, d, hydrate) for d in cursor]

    def count(self, model, flt: dict | None = None) -> int:
        return int(self._coll(model).count_documents(_flt(flt)))

    # ---- writes ------------------------------------------------------------------------------------------------
    def add(self, obj):
        """Insert a new document and give the object its id."""
        model = type(obj)
        if obj.id is None:
            obj.id = self.next_id(model.collection)
        doc = encode(obj.to_doc())
        doc["_id"] = obj.id
        self._coll(model).insert_one(doc)
        return obj

    def save(self, obj):
        """Replace the whole stored document with the object's current state."""
        doc = encode(obj.to_doc())
        self._coll(type(obj)).replace_one({"_id": obj.id}, doc)
        return obj

    def update(self, model, obj_id: int, fields: dict) -> None:
        self._coll(model).update_one({"_id": obj_id}, {"$set": encode(fields)})

    def update_many(self, model, flt: dict, fields: dict) -> None:
        self._coll(model).update_many(_flt(flt), {"$set": encode(fields)})

    def push(self, model, obj_id: int, field: str, value: Any) -> None:
        self._coll(model).update_one({"_id": obj_id}, {"$push": {field: encode(value)}})

    def delete(self, model, flt: dict) -> int:
        return int(self._coll(model).delete_many(_flt(flt)).deleted_count)

    # ---- housekeeping ------------------------------------------------------------------------------------------
    def ensure_indexes(self) -> None:
        from backend.app.models import ALL_MODELS

        for model in ALL_MODELS:
            coll = self._coll(model)
            for keys, opts in model.indexes:
                coll.create_index(keys, **opts)

    def drop_all_data(self) -> None:
        from backend.app.models import ALL_MODELS

        for model in ALL_MODELS:
            self._coll(model).delete_many({})
        self.database["_counters"].delete_many({})
