"""SC005: real (not synthetic) fixed-camera footage, scored against an empty-room reference photo.

Ground truth is read off the clip by eye: 3 people (1 standing, 2 seated), 6 chairs (2 occupied), 3 machines.
This is one 10-second clip, so it checks that the reference-photo path works; it does not measure accuracy.
"""
import shutil
import tempfile
from pathlib import Path

import cv2
import pytest

from vision.infra_detector import Layout
from vision.pipeline import analyse_centre, analyse_video
from vision.config import load_config

DATA = Path("data")
pytestmark = pytest.mark.skipif(not (DATA / "videos" / "SC005.mp4").exists(), reason="SC005 footage not present")


def test_sc005_counts_people_chairs_machines():
    r = analyse_centre("SC005", DATA)
    assert r.estimated_count == 3
    assert r.items_detected == {"chair": 6, "machine": 3}
    assert not r.items_not_operable  # no indicator lamps defined, so nothing may be called "not operable"


def test_sc005_detects_a_chair_missing_from_the_room():
    """Paint a chair out of the reference photo: the live clip then differs there, as if the chair had been removed.
    (A stand-in: the clip itself cannot be edited, so the reference is changed instead.)"""
    layout = Layout.load(DATA / "layouts" / "SC005.json")
    zone = next(s for s in layout.slots if s.id == "chair-5").box
    ref = cv2.imread(str(DATA / "reference" / "SC005.png"))
    x, y, w, h = zone
    ref[y:y + h, x:x + w] = (215, 215, 215)  # blank light patch where the dark chair stands
    with tempfile.TemporaryDirectory() as tmp:
        ref_path = Path(tmp) / "ref.png"
        cv2.imwrite(str(ref_path), ref)
        r = analyse_video(DATA / "videos" / "SC005.mp4", "SC005", layout, ref_path, load_config("normal"))
    assert r.items_detected.get("chair") == 5


def test_demo_layouts_keep_the_old_semantics():
    layout = Layout.load(DATA / "layouts" / "SC001.json")
    assert layout.reference_has_equipment is False and layout.person_detector is None


def test_upload_analysis_with_a_full_resolution_photo():
    """The web upload path: a photo whose resolution differs from the clip (848 vs 1280 wide), zones drawn in its pixels."""
    from vision.upload_analysis import analyse_upload
    from vision.types import VideoError

    cap = cv2.VideoCapture(str(DATA / "real_footage_source" / "SC005_empty_room.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 120)
    ok, frame = cap.read()
    assert ok
    layout = Layout.load(DATA / "layouts" / "SC005.json")
    k = frame.shape[1] / layout.frame_size[0]  # layout zones are in 848-wide pixels; scale to the photo
    zones = [{"item_type": s.item_type, "box": [int(v * k) for v in s.box]} for s in layout.slots]
    with tempfile.TemporaryDirectory() as tmp:
        photo = Path(tmp) / "photo.png"
        cv2.imwrite(str(photo), frame)
        r, counts = analyse_upload(DATA / "videos" / "SC005.mp4", photo, zones, "SC005", load_config("normal"), None)
        assert counts == {"chair": 6, "machine": 3}
        assert r.estimated_count == 3 and r.items_detected == {"chair": 6, "machine": 3}
        # no zones: people are still counted, equipment is not checked
        r2, c2 = analyse_upload(DATA / "videos" / "SC005.mp4", photo, [], "SC005", load_config("normal"), None)
        assert c2 == {} and r2.estimated_count == 3 and r2.items_detected == {}
        # a photo of the wrong shape is refused with a readable message
        cv2.imwrite(str(photo), cv2.resize(frame, (600, 600)))
        with pytest.raises(VideoError, match="different shapes"):
            analyse_upload(DATA / "videos" / "SC005.mp4", photo, [], "SC005", load_config("normal"), None)
