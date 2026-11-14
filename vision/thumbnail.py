"""Build the small, privacy-safe, annotated thumbnail that is the only image ever stored or uploaded."""
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from vision.config import VisionConfig
from vision.privacy import pixelate_boxes
from vision.sampler import resize_to_width
from vision.types import PersonBox, Slot, SlotResult

GREEN, RED, ORANGE = (60, 180, 60), (50, 50, 220), (0, 140, 255)


def annotate(image: np.ndarray, boxes: list[PersonBox], slots: list[Slot], results: list[SlotResult],
             estimated: int, label: str) -> np.ndarray:
    out = pixelate_boxes(image, boxes)  # people are pixelated BEFORE any drawing or saving
    by_id = {r.slot_id: r for r in results}
    for s in slots:
        r = by_id.get(s.id)
        if r is None:
            continue
        colour = RED if not r.present else ORANGE if r.operability == "not_operable" else GREEN
        x, y, w, h = s.box
        cv2.rectangle(out, (x, y), (x + w, y + h), colour, 2)
    for b in boxes:
        cv2.rectangle(out, (b.x, b.y), (b.x + b.w, b.y + b.h), (255, 255, 255), 1)
    cv2.rectangle(out, (0, 0), (out.shape[1], 18), (30, 30, 30), -1)
    cv2.putText(out, f"{label}  people~{estimated}  green=present red=missing orange=not operable"[:90], (4, 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def save_thumbnail(img: np.ndarray, cfg: VisionConfig, out_dir: Path, centre_code: str) -> tuple[str, int]:
    """Write a downscaled JPEG; return (path relative to the data folder, size in bytes)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    small = resize_to_width(img, cfg.thumb_width)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    name = f"{centre_code}_{stamp}.jpg"
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, cfg.jpeg_quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    (out_dir / name).write_bytes(buf.tobytes())
    return f"thumbnails/{name}", len(buf)
