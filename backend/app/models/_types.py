"""Shared helpers for the document models."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(kw_only=True, eq=False)
class Doc:
    """Base of every stored document. `indexes` lists (keys, options) passed to MongoDB create_index."""
    collection: ClassVar[str]
    indexes: ClassVar[list] = []
    id: int | None = None
