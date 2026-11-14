"""Person counting. Aggregate counts only: no identity, no tracking, no face analysis.

Two interchangeable backends:
  * MotionPersonCounter - background-subtraction blobs; works on the synthetic demo footage.
  * YoloPersonCounter   - YOLOv8n 'person' class; intended for real footage (CPU).
"""
import logging
import statistics
from typing import Protocol

import cv2
import numpy as np

from vision.config import VisionConfig
from vision.types import PersonBox

log = logging.getLogger("vision.persons")


class PersonCounter(Protocol):
    def prepare(self, images: list[np.ndarray]) -> None: ...
    def detect(self, image: np.ndarray, index: int) -> list[PersonBox]: ...


def rolling_median(values: list[int], window: int) -> list[int]:
    """Trailing median to damp frame-to-frame flicker."""
    window = max(1, window)
    out: list[int] = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        out.append(int(round(statistics.median(chunk))))
    return out


def total(boxes: list[PersonBox]) -> int:
    return sum(b.count for b in boxes)


class MotionPersonCounter:
    """Counts moving blobs against a median background built from the sampled frames."""

    def __init__(self, cfg: VisionConfig):
        self.cfg = cfg
        self._background: np.ndarray | None = None

    def prepare(self, images: list[np.ndarray]) -> None:
        if len(images) < 3:
            log.warning("Only %d frames: median background will be unreliable", len(images))
        blurred = [cv2.GaussianBlur(im, (5, 5), 0) for im in images]
        self._background = np.median(np.stack(blurred), axis=0).astype(np.uint8)

    def detect(self, image: np.ndarray, index: int) -> list[PersonBox]:
        if self._background is None:
            raise RuntimeError("prepare() must be called before detect()")
        cfg = self.cfg
        diff = np.abs(cv2.GaussianBlur(image, (5, 5), 0).astype(np.int16) - self._background.astype(np.int16)).max(axis=2)
        mask = (diff > cfg.fg_threshold).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 9)))
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        typical = cfg.typical_person_area * cfg.scale_area
        min_area = cfg.min_blob_area * cfg.scale_area
        boxes: list[PersonBox] = []
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < min_area:
                continue
            count = max(1, int(round(area / typical))) if area > cfg.split_ratio * typical else 1
            boxes.append(PersonBox(x, y, w, h, count))
        return boxes


def _merge_close(boxes: list[PersonBox], pad: int) -> list[PersonBox]:
    """Merge boxes whose padded rectangles touch, so one seated person split by a desk or chair counts once.
    Side effect: two people standing very close together also merge (an under-count)."""
    boxes = list(boxes)
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a.x - pad < b.x + b.w and b.x - pad < a.x + a.w and a.y - pad < b.y + b.h and b.y - pad < a.y + a.h:
                    x0, y0 = min(a.x, b.x), min(a.y, b.y)
                    x1, y1 = max(a.x + a.w, b.x + b.w), max(a.y + a.h, b.y + b.h)
                    boxes[i] = PersonBox(x0, y0, x1 - x0, y1 - y0, 1)
                    del boxes[j]
                    changed = True
                    break
            if changed:
                break
    return boxes


class ReferencePersonCounter:
    """Counts people as foreground blobs against an empty-room reference photo from the same fixed camera.

    Unlike MotionPersonCounter it also sees people who sit still (a reference image does not depend on movement).
    Limits: needs a fixed camera and a clean empty-room reference; people who touch or overlap merge into one blob
    (so it can under-count); moved furniture or lighting changes show up as false people. Blobs whose area is below
    `ref_min_area_frac` of the frame are ignored.
    """

    def __init__(self, cfg: VisionConfig, reference: np.ndarray):
        self.cfg = cfg
        self._reference = reference
        self._ref_blur: np.ndarray | None = None

    def prepare(self, images: list[np.ndarray]) -> None:
        h, w = images[0].shape[:2]
        ref = cv2.resize(self._reference, (w, h), interpolation=cv2.INTER_AREA)
        self._ref_blur = cv2.GaussianBlur(ref, (9, 9), 0).astype(np.int16)

    def detect(self, image: np.ndarray, index: int) -> list[PersonBox]:
        if self._ref_blur is None:
            raise RuntimeError("prepare() must be called before detect()")
        cfg = self.cfg
        h, w = image.shape[:2]
        diff = np.abs(cv2.GaussianBlur(image, (9, 9), 0).astype(np.int16) - self._ref_blur).max(axis=2)
        mask = (diff > cfg.ref_diff_threshold).astype(np.uint8) * 255
        k = max(3, int(round(w * 0.0177)) | 1)  # about 15 px at 848 wide
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((max(3, k // 2), max(3, k // 2)), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        min_area = cfg.ref_min_area_frac * w * h
        boxes = []
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if area >= min_area:
                boxes.append(PersonBox(x, y, bw, bh, 1))
        return _merge_close(boxes, int(round(w * 0.025)))


class YoloPersonCounter:
    """YOLO 'person' detections above a confidence threshold (CPU inference)."""

    def __init__(self, cfg: VisionConfig, backend=None):
        from vision.yolo_backend import YoloBackend  # imported lazily: ultralytics is heavy
        self.cfg = cfg
        self.backend = backend or YoloBackend(cfg)
        self.cache: dict[int, list] = {}  # frame index -> all detections, reused for equipment counts

    def prepare(self, images: list[np.ndarray]) -> None:
        return None

    def detect(self, image: np.ndarray, index: int) -> list[PersonBox]:
        detections = self.backend.detect(image)
        self.cache[index] = detections
        return [PersonBox(*d.box) for d in detections if d.label == "person"]


def make_person_counter(cfg: VisionConfig, reference: np.ndarray | None = None) -> PersonCounter:
    if cfg.person_detector == "motion":
        return MotionPersonCounter(cfg)
    if cfg.person_detector == "reference":
        if reference is None:
            raise ValueError("person_detector='reference' needs an empty-room reference image")
        return ReferencePersonCounter(cfg, reference)
    if cfg.person_detector == "yolo":
        return YoloPersonCounter(cfg)
    raise ValueError(f"Unknown person detector '{cfg.person_detector}' (use 'motion', 'reference' or 'yolo')")
