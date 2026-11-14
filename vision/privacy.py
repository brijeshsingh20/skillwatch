"""Privacy helpers: person regions are pixelated before anything is saved."""
import cv2
import numpy as np

from vision.types import PersonBox


def pixelate_boxes(img: np.ndarray, boxes: list[PersonBox], pad: int = 4, block: int = 6) -> np.ndarray:
    """Return a copy with every person region replaced by coarse blocks (no face or body detail survives)."""
    out = img.copy()
    h, w = out.shape[:2]
    for b in boxes:
        x0, y0 = max(0, b.x - pad), max(0, b.y - pad)
        x1, y1 = min(w, b.x + b.w + pad), min(h, b.y + b.h + pad)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        region = out[y0:y1, x0:x1]
        small = cv2.resize(region, (max(1, (x1 - x0) // block), max(1, (y1 - y0) // block)), interpolation=cv2.INTER_AREA)
        out[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
    return out
