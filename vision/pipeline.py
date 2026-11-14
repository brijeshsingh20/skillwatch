"""Video analytics pipeline: sample -> count people -> check equipment -> annotated thumbnail.

CLI:  python -m vision.pipeline --centre SC001 [--video path] [--profile normal|lowbw] [--data-dir data]
It also exposes `analyse_video` for the API-triggered job.
"""
import argparse
import json
import logging
import statistics
import time
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from vision.config import VisionConfig, load_config
from vision.infra_detector import Layout, SlotTracker, load_reference, summarise
from vision.person_counter import YoloPersonCounter, make_person_counter, rolling_median, total
from vision.quality import frame_quality
from vision.sampler import sample_frames
from vision.thumbnail import annotate, save_thumbnail
from vision.types import PipelineResult, VideoError

log = logging.getLogger("vision.pipeline")


SMALL_ITEM_TYPES = ("chair",)


def _inside_any(box, zones, fraction: float = 0.8) -> bool:
    """True when at least `fraction` of the box lies inside one zone (so it is no bigger than that item's spot)."""
    for zx, zy, zw, zh in zones:
        ix = max(0, min(box.x + box.w, zx + zw) - max(box.x, zx))
        iy = max(0, min(box.y + box.h, zy + zh) - max(box.y, zy))
        if ix * iy >= fraction * box.w * box.h:
            return True
    return False


def analyse_video(video_path: str | Path, centre_code: str, layout: Layout, reference_path: str | Path,
                  cfg: VisionConfig, thumb_dir: str | Path | None = None, counter=None) -> PipelineResult:
    started = time.perf_counter()
    notes: list[str] = []
    frames = list(sample_frames(video_path, cfg.frame_interval_s, cfg.width, cfg.max_frames, cfg.min_frames))
    if not frames:
        raise VideoError(f"No frames could be read from {video_path}")
    if len(frames) < cfg.min_frames:
        notes.append(f"Only {len(frames)} frame(s) available (wanted {cfg.min_frames}); counts and equipment checks are less reliable")
    images = [f.image for f in frames]
    h, w = images[0].shape[:2]

    quality = round(statistics.median(frame_quality(im) for im in images), 3)
    low_quality = quality < cfg.low_quality_threshold
    if low_quality:
        notes.append(f"Low image quality ({quality:.2f} < {cfg.low_quality_threshold}); counts are less reliable")

    reference = load_reference(reference_path, w, h)
    if counter is None:
        if layout.person_detector and cfg.person_detector == "motion":  # layout may pick the detector; env/CLI choice wins
            cfg = replace(cfg, person_detector=layout.person_detector)
        counter = make_person_counter(cfg, reference)
    counter.prepare(images)
    per_frame_boxes = [counter.detect(im, f.index) for im, f in zip(images, frames)]
    if layout.reference_has_equipment:
        # A chair taken out of the room leaves a chair-sized change that is not a person: do not count or mask it.
        chair_boxes = [s.box for s in layout.scaled(w, h) if s.item_type in SMALL_ITEM_TYPES]
        per_frame_boxes = [[b for b in boxes if not _inside_any(b, chair_boxes)] for boxes in per_frame_boxes]
    raw = [total(b) for b in per_frame_boxes]
    smoothed = rolling_median(raw, cfg.smoothing_window)
    estimated = int(round(statistics.median(smoothed)))

    # Equipment: zone method for slots; YOLO counts for types configured as "yolo" (and supported by COCO).
    yolo_types = {t for t, m in cfg.infra_methods.items() if m == "yolo" and t in cfg.coco_item_map.values()}
    slots = [s for s in layout.scaled(w, h) if s.item_type not in yolo_types]
    tracker = SlotTracker(slots, cfg, layout.reference_has_equipment)
    for im, boxes in zip(images, per_frame_boxes):
        tracker.add_frame(im, reference, boxes)
    results = tracker.results()
    detected, not_operable = summarise(results)

    if yolo_types:
        cache = getattr(counter, "cache", None)
        if cache is None:
            raise RuntimeError("YOLO equipment counting needs person_detector='yolo' so detections can be shared")
        per_type: dict[str, list[int]] = {t: [] for t in yolo_types}
        for f in frames:
            c = Counter(cfg.coco_item_map[d.label] for d in cache.get(f.index, []) if d.label in cfg.coco_item_map)
            for t in yolo_types:
                per_type[t].append(c.get(t, 0))
        for t, counts in per_type.items():
            detected[t] = int(statistics.median(counts))
        notes.append("Equipment types counted by YOLO: " + ", ".join(sorted(yolo_types)))

    # Confidence: how stable the per-frame counts are, discounted by image quality.
    stability = 1.0 - min(1.0, sum(abs(r - estimated) for r in raw) / len(raw) / max(1, estimated))
    confidence = round(max(0.0, min(1.0, stability * (0.5 + 0.5 * quality))), 3)

    frame_ref, thumb_bytes = None, 0
    if thumb_dir is not None:
        rep = min(range(len(raw)), key=lambda i: (abs(raw[i] - estimated), i))
        thumb = annotate(images[rep], per_frame_boxes[rep], slots, results, estimated, centre_code)
        frame_ref, thumb_bytes = save_thumbnail(thumb, cfg, Path(thumb_dir), centre_code)

    return PipelineResult(
        centre_code=centre_code, video=str(video_path), frames_used=len(frames), estimated_count=estimated,
        raw_counts=raw, smoothed_counts=smoothed, items_detected=detected, items_not_operable=not_operable,
        slot_results=results, confidence=confidence, frame_quality=quality, low_quality=low_quality,
        frame_ref=frame_ref, thumb_bytes=thumb_bytes, processing_seconds=round(time.perf_counter() - started, 2),
        notes=notes,
    )


def analyse_centre(centre_code: str, data_dir: str | Path = "data", profile: str = "normal",
                   video: str | Path | None = None, **overrides) -> PipelineResult:
    """Convenience wrapper using the standard data/ folder layout."""
    data = Path(data_dir)
    cfg = load_config(profile, **overrides)
    layout = Layout.load(data / "layouts" / f"{centre_code}.json")
    return analyse_video(video or data / "videos" / f"{centre_code}.mp4", centre_code, layout,
                         data / "reference" / f"{centre_code}.png", cfg, thumb_dir=data / "thumbnails")


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Run the SkillWatch vision pipeline on one centre's clip")
    p.add_argument("--centre", required=True)
    p.add_argument("--video")
    p.add_argument("--profile", default="normal", choices=["normal", "lowbw"])
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()
    try:
        result = analyse_centre(args.centre, args.data_dir, args.profile, args.video)
    except (VideoError, FileNotFoundError) as exc:
        log.error("%s", exc)
        raise SystemExit(1)
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
