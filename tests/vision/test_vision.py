import json

import cv2
import numpy as np
import pytest

from scripts.generate_demo_footage import generate_centre
from scripts.scenario import SCENARIO
from vision.config import load_config
from vision.person_counter import MotionPersonCounter, YoloPersonCounter, rolling_median
from vision.pipeline import analyse_centre
from vision.privacy import pixelate_boxes
from vision.quality import frame_quality
from vision.sampler import sample_frames
from vision.types import PersonBox, VideoError
from vision.yolo_backend import Detection


def _write_video(path, frames=40, fps=10, size=(320, 240)):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for i in range(frames):
        img = np.full((size[1], size[0], 3), 120, np.uint8)
        cv2.circle(img, (10 + i * 5, 100), 12, (0, 0, 255), -1)
        w.write(img)
    w.release()


def test_sampler_interval_and_downscale(tmp_path):
    video = tmp_path / "t.mp4"
    _write_video(video)  # 4 seconds at 10 fps
    frames = list(sample_frames(video, interval_s=1.0, width=160))
    assert len(frames) == 4
    assert frames[0].image.shape[1] == 160
    assert abs(frames[1].timestamp_s - 1.0) < 1e-6


def test_sampler_min_frames_densifies_short_clips(tmp_path):
    video = tmp_path / "short.mp4"
    _write_video(video, frames=40, fps=10)                       # 4 s clip
    assert len(list(sample_frames(video, interval_s=2.0, width=160))) == 2
    assert len(list(sample_frames(video, interval_s=2.0, width=160, min_frames=8))) == 8


def test_sampler_rejects_bad_path(tmp_path):
    with pytest.raises(VideoError):
        list(sample_frames(tmp_path / "missing.mp4", 1.0, 320))


def test_rolling_median_damps_flicker():
    assert rolling_median([10, 10, 14, 10, 10], 3) == [10, 10, 10, 10, 10]


def test_pixelate_removes_detail_only_inside_box():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    out = pixelate_boxes(img, [PersonBox(20, 20, 30, 40)], pad=0, block=10)
    assert np.array_equal(out[80:, 80:], img[80:, 80:])
    assert out[20:60, 20:50].std() < img[20:60, 20:50].std() * 0.5


def test_motion_counter_counts_blobs():
    cfg = load_config()
    bg = np.full((240, 320, 3), 150, np.uint8)
    images = []
    for shift in range(5):
        im = bg.copy()
        for k in range(3):  # three 'people', moving between frames
            x, y = 40 + k * 90 + shift * 20, 60 + shift * 9  # moves further than its own width between samples
            cv2.rectangle(im, (x, y), (x + 18, y + 40), (200, 40, 40), -1)
        images.append(im)
    counter = MotionPersonCounter(cfg)
    counter.prepare(images)
    assert sum(b.count for b in counter.detect(images[2], 2)) == 3


def test_yolo_counter_uses_person_class_only():
    class Stub:
        def detect(self, image):
            return [Detection("person", 0.9, (1, 1, 10, 20)), Detection("person", 0.8, (30, 1, 10, 20)),
                    Detection("chair", 0.9, (50, 50, 20, 20))]

    counter = YoloPersonCounter(load_config(person_detector="yolo"), backend=Stub())
    boxes = counter.detect(np.zeros((100, 100, 3), np.uint8), 0)
    assert len(boxes) == 2 and 0 in counter.cache


def test_quality_score_drops_for_blurry_noisy_image():
    rng = np.random.default_rng(1)
    sharp = np.full((240, 320, 3), 150, np.uint8)
    for i in range(0, 320, 40):
        cv2.rectangle(sharp, (i, 20), (i + 25, 200), (40, 80, 160), -1)
    bad = cv2.GaussianBlur(sharp, (15, 15), 0)
    bad = np.clip((bad.astype(np.float32) - 128) * 0.6 + 128 + rng.normal(0, 6, bad.shape), 0, 255).astype(np.uint8)
    assert frame_quality(sharp) > frame_quality(bad)


@pytest.fixture(scope="module")
def demo_data(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    for sc in SCENARIO:
        generate_centre(sc, root, duration_s=24, fps=8)
    return root


@pytest.mark.parametrize("code", [sc["code"] for sc in SCENARIO])
def test_pipeline_matches_ground_truth(demo_data, code):
    truth = json.loads((demo_data / "ground_truth" / f"{code}.json").read_text())
    res = analyse_centre(code, demo_data)
    assert abs(res.estimated_count - truth["true_count"]) <= 1
    assert res.items_detected == truth["present"]
    assert res.items_not_operable == truth["not_operable"]
    assert res.low_quality == (truth["camera_profile"] == "poor")
    assert res.frame_ref and (demo_data / res.frame_ref).exists()
    assert 0.0 <= res.confidence <= 1.0


def test_lowbw_profile_shrinks_thumbnail(demo_data):
    normal = analyse_centre("SC002", demo_data)
    low = analyse_centre("SC002", demo_data, profile="lowbw")
    assert low.thumb_bytes < normal.thumb_bytes
    assert abs(low.estimated_count - 8) <= 1


def test_pipeline_missing_video_raises(demo_data):
    with pytest.raises(VideoError):
        analyse_centre("SC001", demo_data, video=demo_data / "nope.mp4")


def test_lowbw_on_short_clip_does_not_invent_missing_equipment(tmp_path):
    """Regression: a 16 s clip gave the low-bandwidth profile only 4 frames and a false 'chair missing'."""
    sc = next(s for s in SCENARIO if s["code"] == "SC002")
    generate_centre(sc, tmp_path, duration_s=16, fps=8)
    res = analyse_centre("SC002", tmp_path, profile="lowbw")
    assert res.frames_used >= 8
    assert res.items_detected == sc["present"]
