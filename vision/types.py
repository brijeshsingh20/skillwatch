"""Plain data containers shared across the vision modules."""
from dataclasses import dataclass, field

import numpy as np


class VideoError(RuntimeError):
    """Raised when a video can't be opened or yields no usable frames."""


@dataclass(frozen=True)
class Frame:
    index: int
    timestamp_s: float
    image: np.ndarray  # BGR, already downscaled


@dataclass(frozen=True)
class PersonBox:
    """A person region. `count` > 1 means a merged blob split by the area heuristic."""
    x: int
    y: int
    w: int
    h: int
    count: int = 1


@dataclass(frozen=True)
class Slot:
    id: str
    item_type: str
    box: tuple[int, int, int, int]
    indicator: tuple[int, int, int, int] | None = None


@dataclass
class SlotResult:
    slot_id: str
    item_type: str
    present: bool
    present_ratio: float
    valid_frames: int
    operability: str  # "operable" | "not_operable" | "unknown" | "absent" | "not_checked"
    led_ratio: float | None = None


@dataclass
class PipelineResult:
    centre_code: str
    video: str
    frames_used: int
    estimated_count: int
    raw_counts: list[int]
    smoothed_counts: list[int]
    items_detected: dict[str, int]
    items_not_operable: dict[str, int]
    slot_results: list[SlotResult]
    confidence: float
    frame_quality: float
    low_quality: bool
    frame_ref: str | None
    thumb_bytes: int
    processing_seconds: float
    notes: list[str] = field(default_factory=list)
