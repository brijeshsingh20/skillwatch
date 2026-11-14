"""A small in-memory stand-in for a pymongo Database, for tests that run without a MongoDB server.

It implements only what backend/app/db/store.py uses: insert_one, find_one, find().sort().limit(), replace_one,
update_one/update_many ($set, $push, $inc, upsert), find_one_and_update, delete_one/delete_many, count_documents and
create_index (unique and sparse are enforced). Filters support equality and $in, $nin, $ne, $gt, $gte, $lt, $lte.

To run the backend tests against a REAL MongoDB instead, set SKILLWATCH_TEST_MONGO_URL (see tests/conftest.py).
"""
from __future__ import annotations

import copy

from backend.app.db.store import DuplicateKeyError

_OPS = {
    "$in": lambda v, a: v in a,
    "$nin": lambda v, a: v not in a,
    "$ne": lambda v, a: v != a,
    "$gt": lambda v, a: v is not None and v > a,
    "$gte": lambda v, a: v is not None and v >= a,
    "$lt": lambda v, a: v is not None and v < a,
    "$lte": lambda v, a: v is not None and v <= a,
}


def _matches(doc: dict, flt: dict) -> bool:
    for key, cond in flt.items():
        value = doc.get(key)
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                if op not in _OPS:
                    raise NotImplementedError(f"fake_mongo does not support {op}")
                if not _OPS[op](value, arg):
                    return False
        elif value != cond:
            return False
    return True


class _Result:
    def __init__(self, deleted_count=0, matched_count=0, modified_count=0):
        self.deleted_count, self.matched_count, self.modified_count = deleted_count, matched_count, modified_count


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, keys):
        for key, direction in reversed(keys):
            self._docs.sort(key=lambda d, k=key: (d.get(k) is not None, d.get(k)), reverse=direction < 0)
        return self

    def limit(self, n):
        if n:
            self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(copy.deepcopy(self._docs))


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self.unique: list[tuple[list[str], bool]] = []  # (fields, sparse)

    def create_index(self, keys, unique=False, sparse=False, **_):
        if unique:
            self.unique.append(([k for k, _ in keys], sparse))
        return "idx"

    def _check_unique(self, doc, ignore_id=None):
        for fields, sparse in self.unique:
            if sparse and any(f not in doc for f in fields):
                continue
            for other in self.docs:
                if other["_id"] == ignore_id:
                    continue
                if all(other.get(f) == doc.get(f) for f in fields):
                    raise DuplicateKeyError(f"duplicate key on {fields}")

    def insert_one(self, doc):
        doc = copy.deepcopy(doc)
        if any(d["_id"] == doc["_id"] for d in self.docs):
            raise DuplicateKeyError("duplicate _id")
        self._check_unique(doc)
        self.docs.append(doc)

    def find(self, flt=None):
        return _Cursor([d for d in self.docs if _matches(d, flt or {})])

    def find_one(self, flt=None):
        for d in self.docs:
            if _matches(d, flt or {}):
                return copy.deepcopy(d)
        return None

    def count_documents(self, flt=None):
        return sum(1 for d in self.docs if _matches(d, flt or {}))

    def replace_one(self, flt, new):
        for i, d in enumerate(self.docs):
            if _matches(d, flt):
                new = copy.deepcopy(new)
                new["_id"] = d["_id"]
                self._check_unique(new, ignore_id=d["_id"])
                self.docs[i] = new
                return _Result(matched_count=1, modified_count=1)
        return _Result()

    def _apply(self, d, update):
        for op, fields in update.items():
            for k, v in fields.items():
                if op == "$set":
                    d[k] = copy.deepcopy(v)
                elif op == "$push":
                    d.setdefault(k, []).append(copy.deepcopy(v))
                elif op == "$inc":
                    d[k] = d.get(k, 0) + v
                else:
                    raise NotImplementedError(f"fake_mongo does not support {op}")

    def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _matches(d, flt):
                self._apply(d, update)
                return _Result(matched_count=1, modified_count=1)
        if upsert:
            d = {k: v for k, v in flt.items() if not isinstance(v, dict)}
            self._apply(d, update)
            self.docs.append(d)
        return _Result()

    def update_many(self, flt, update):
        n = 0
        for d in self.docs:
            if _matches(d, flt):
                self._apply(d, update)
                n += 1
        return _Result(matched_count=n, modified_count=n)

    def find_one_and_update(self, flt, update, upsert=False, return_document=True):
        self.update_one(flt, update, upsert=upsert)
        return self.find_one(flt)

    def delete_many(self, flt):
        keep = [d for d in self.docs if not _matches(d, flt)]
        n = len(self.docs) - len(keep)
        self.docs = keep
        return _Result(deleted_count=n)

    def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _matches(d, flt):
                del self.docs[i]
                return _Result(deleted_count=1)
        return _Result()


class FakeDatabase:
    def __init__(self):
        self._colls: dict[str, FakeCollection] = {}

    def __getitem__(self, name):
        return self._colls.setdefault(name, FakeCollection())
