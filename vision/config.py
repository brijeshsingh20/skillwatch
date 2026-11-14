"""Vision pipeline settings. Every value can be overridden with a VISION_* environment variable."""
import os
from dataclasses import dataclass, field, replace


def _env(name: str, default, cast=str):
    raw = os.getenv(f"VISION_{name}")
    return cast(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class VisionConfig:
    # Sampling / low-bandwidth knobs
    frame_interval_s: float = 2.0
    width: int = 640                 # frames are downscaled to this width (never upscaled)
    jpeg_quality: int = 80           # thumbnail quality
    thumb_width: int = 320
    max_frames: int = 60
    min_frames: int = 8              # short clips are sampled more densely so votes and background stay stable
    # Person counting
    person_detector: str = "motion"  # "motion" (synthetic demo) | "reference" (fixed camera + empty-room photo) | "yolo"
    person_conf: float = 0.35
    smoothing_window: int = 5
    yolo_model: str = "yolov8n.pt"
    yolo_imgsz: int = 640
    # Reference counter (foreground vs empty-room photo): colour-difference threshold, min blob area as frame fraction
    ref_diff_threshold: int = 45
    ref_min_area_frac: float = 0.0037
    # Motion counter calibration (areas defined at 640 px width, scaled automatically)
    typical_person_area: float = 650.0
    min_blob_area: float = 180.0
    split_ratio: float = 1.6
    fg_threshold: int = 35
    # Infrastructure
    infra_methods: dict = field(default_factory=lambda: {"chair": "zone", "workbench": "zone", "machine": "zone"})
    zone_diff_threshold: int = 45
    zone_changed_fraction: float = 0.35
    min_valid_pixel_fraction: float = 0.5
    person_mask_pad: int = 5
    led_brightness_threshold: int = 140
    operability_types: tuple = ("machine",)
    operable_vote_fraction: float = 0.6
    # Camera quality (calibrated on synthetic clips; recalibrate on real cameras)
    low_quality_threshold: float = 0.85
    # Names must match COCO classes for the YOLO item path
    coco_item_map: dict = field(default_factory=lambda: {"chair": "chair", "bench": "workbench", "dining table": "workbench"})

    @property
    def scale_area(self) -> float:
        return (self.width / 640.0) ** 2


PROFILES = {
    "normal": {},
    # Cheaper settings for poor links: fewer frames, smaller images, stronger compression.
    "lowbw": {"frame_interval_s": 4.0, "width": 320, "jpeg_quality": 50, "thumb_width": 224, "yolo_imgsz": 416},
}


def load_config(profile: str = "normal", **overrides) -> VisionConfig:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Choose from {sorted(PROFILES)}")
    base = VisionConfig(**PROFILES[profile])
    env = {
        "frame_interval_s": _env("FRAME_INTERVAL", base.frame_interval_s, float),
        "width": _env("WIDTH", base.width, int),
        "jpeg_quality": _env("JPEG_QUALITY", base.jpeg_quality, int),
        "person_detector": _env("PERSON_DETECTOR", base.person_detector),
        "person_conf": _env("PERSON_CONF", base.person_conf, float),
        "smoothing_window": _env("SMOOTHING_WINDOW", base.smoothing_window, int),
    }
    return replace(base, **{**env, **overrides})
