"""Thin wrapper around Ultralytics YOLO (CPU). Only imported when the YOLO path is used.

Weights (yolov8n.pt, ~6 MB) are downloaded by Ultralytics on first use, so the first run needs internet.
"""
import logging
from dataclasses import dataclass

import numpy as np

from vision.config import VisionConfig

log = logging.getLogger("vision.yolo")


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # x, y, w, h


class YoloBackend:
    WANTED = {"person", "chair", "bench", "dining table"}

    def __init__(self, cfg: VisionConfig):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed. Run: pip install -r requirements.txt") from exc
        self.cfg = cfg
        self.model = YOLO(cfg.yolo_model)
        log.info("Loaded %s on CPU", cfg.yolo_model)

    def detect(self, image: np.ndarray) -> list[Detection]:
        result = self.model.predict(image, imgsz=self.cfg.yolo_imgsz, conf=self.cfg.person_conf,
                                    device="cpu", verbose=False)[0]
        names = result.names
        out: list[Detection] = []
        for box in result.boxes:
            label = names[int(box.cls[0])]
            if label not in self.WANTED:
                continue
            x0, y0, x1, y1 = (int(v) for v in box.xyxy[0].tolist())
            out.append(Detection(label, float(box.conf[0]), (x0, y0, x1 - x0, y1 - y0)))
        return out
