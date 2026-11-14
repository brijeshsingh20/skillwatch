"""Frame sampling and downscaling. Raw frames stay in memory; nothing is written to disk here."""
import logging
from collections.abc import Iterator
from pathlib import Path

import cv2

from vision.types import Frame, VideoError

log = logging.getLogger("vision.sampler")


def resize_to_width(img, width: int):
    h, w = img.shape[:2]
    if w <= width:
        return img
    return cv2.resize(img, (width, int(round(h * width / w))), interpolation=cv2.INTER_AREA)


def sample_frames(path: str | Path, interval_s: float, width: int, max_frames: int | None = None,
                  min_frames: int = 1) -> Iterator[Frame]:
    """Yield one frame every `interval_s` seconds, downscaled to `width` px.

    `min_frames` guards short clips: the person counter and equipment votes need several frames to build a stable
    background, so if the interval would give fewer, the step is shortened (only possible when the clip length is known).
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError(f"Cannot open video: {path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps != fps or fps <= 0:
            fps = 25.0
            log.warning("FPS unknown for %s, assuming %.0f", path, fps)
        step = max(1, int(round(fps * interval_s)))
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if min_frames > 1 and total and total > 0 and total // step < min_frames:
            step = max(1, int(total // min_frames))
            log.info("Clip is short: sampling every %d frames to reach at least %d frames", step, min_frames)
        idx, yielded = 0, 0
        while True:
            if not cap.grab():
                break
            if idx % step == 0:
                ok, img = cap.retrieve()
                if ok and img is not None:
                    yield Frame(idx, idx / fps, resize_to_width(img, width))
                    yielded += 1
                    if max_frames and yielded >= max_frames:
                        break
            idx += 1
    finally:
        cap.release()
