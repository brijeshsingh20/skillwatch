"""Analyse one uploaded clip against one uploaded photo of the empty workplace (same camera view).

Kept free of any web or database code so it can be tested on its own. User-facing problems raise VideoError with a
message that can be shown as-is.
"""
from pathlib import Path

import cv2

from vision.config import VisionConfig
from vision.infra_detector import Layout
from vision.pipeline import analyse_video
from vision.types import PipelineResult, Slot, VideoError

MAX_ASPECT_DIFF = 0.08  # photo and clip must share the camera's width:height (+/-8%)


def build_layout(zones: list[dict], photo_w: int, photo_h: int) -> tuple[Layout, dict[str, int]]:
    """Zones are {"item_type", "box": [x, y, w, h]} in the photo's pixels. Returns the layout and zones per type."""
    counts: dict[str, int] = {}
    slots = []
    for z in zones:
        t = z["item_type"]
        x, y, w, h = z["box"]
        if x >= photo_w or y >= photo_h:
            raise VideoError("A zone lies outside the photo; redraw the zones.")
        counts[t] = counts.get(t, 0) + 1
        slots.append(Slot(f"{t}-{counts[t]}", t, (x, y, min(w, photo_w - x), min(h, photo_h - y))))
    return Layout((photo_w, photo_h), slots, person_detector="reference", reference_has_equipment=True), counts


def analyse_upload(video_path: str | Path, photo_path: str | Path, zones: list[dict], centre_code: str,
                   cfg: VisionConfig, thumb_dir: str | Path | None) -> tuple[PipelineResult, dict[str, int]]:
    photo = cv2.imread(str(photo_path))
    if photo is None:
        raise VideoError("The empty-room photo could not be read as an image (use JPG or PNG).")
    ph, pw = photo.shape[:2]
    cap = cv2.VideoCapture(str(video_path))
    vw, vh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if vw == 0 or vh == 0:
        raise VideoError("The video could not be opened. Try an MP4 (H.264) file.")
    if abs((vw / vh) / (pw / ph) - 1) > MAX_ASPECT_DIFF:
        raise VideoError(f"The photo ({pw}x{ph}) and the video ({vw}x{vh}) have different shapes, so they are not the "
                         "same camera view. Use a photo from the camera that recorded the video (or a frame from it).")
    layout, counts = build_layout(zones, pw, ph)
    result = analyse_video(video_path, centre_code, layout, photo_path, cfg, thumb_dir=thumb_dir)
    if not counts:
        result.notes.append("No equipment zones were drawn, so only the head-count was checked.")
    return result, counts
