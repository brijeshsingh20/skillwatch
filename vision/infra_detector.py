"""Infrastructure checks per equipment slot.

* Presence   : zone background-difference against an empty-room reference -> "apparent presence".
* Operability: indicator-lamp brightness for powered equipment            -> "apparent operability".
Pixels covered by detected people are excluded so a person walking past cannot fake or hide equipment.
Neither result is verification; both are visual proxies.
"""
import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from vision.config import VisionConfig
from vision.types import PersonBox, Slot, SlotResult

log = logging.getLogger("vision.infra")


@dataclass(frozen=True)
class Layout:
    frame_size: tuple[int, int]
    slots: list[Slot]
    person_detector: str | None = None  # optional per-centre override, e.g. "reference" for still, seated people
    # True when the reference photo already shows the sanctioned equipment (a normal photo of the room taken with
    # nobody in it). Then a slot is present when its zone MATCHES the reference and absent when it has changed.
    # False (demo default): the reference is a bare room and equipment is whatever differs from it.
    reference_has_equipment: bool = False

    @classmethod
    def load(cls, path: str | Path) -> "Layout":
        data = json.loads(Path(path).read_text())
        slots = [Slot(s["id"], s["item_type"], tuple(s["box"]), tuple(s["indicator"]) if s.get("indicator") else None)
                 for s in data["slots"]]
        return cls(tuple(data["frame_size"]), slots, data.get("person_detector"), bool(data.get("reference_has_equipment", False)))

    def scaled(self, width: int, height: int) -> list[Slot]:
        sx, sy = width / self.frame_size[0], height / self.frame_size[1]

        def sc(b):
            x, y, w, h = b
            return (int(round(x * sx)), int(round(y * sy)), max(1, int(round(w * sx))), max(1, int(round(h * sy))))

        return [Slot(s.id, s.item_type, sc(s.box), sc(s.indicator) if s.indicator else None) for s in self.slots]


def load_reference(path: str | Path, width: int, height: int) -> np.ndarray:
    ref = cv2.imread(str(path))
    if ref is None:
        raise FileNotFoundError(f"Reference image not found or unreadable: {path}")
    return cv2.resize(ref, (width, height), interpolation=cv2.INTER_AREA)


def _person_mask(shape: tuple[int, int], boxes: list[PersonBox], pad: int) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    for b in boxes:
        mask[max(0, b.y - pad): b.y + b.h + pad, max(0, b.x - pad): b.x + b.w + pad] = True
    return mask


class SlotTracker:
    """Collects per-frame votes for every slot, then aggregates them."""

    def __init__(self, slots: list[Slot], cfg: VisionConfig, reference_has_equipment: bool = False):
        self.slots, self.cfg, self.ref_has_equipment = slots, cfg, reference_has_equipment
        self.occluded = {s.id: 0 for s in slots}
        self.present_votes = {s.id: [] for s in slots}
        self.led_votes = {s.id: [] for s in slots}

    def add_frame(self, image: np.ndarray, reference: np.ndarray, boxes: list[PersonBox]) -> None:
        cfg = self.cfg
        blurred = cv2.GaussianBlur(image, (5, 5), 0)
        diff = np.abs(blurred.astype(np.int16) - reference.astype(np.int16)).max(axis=2)
        masked = _person_mask(diff.shape, boxes, cfg.person_mask_pad)
        value = image.max(axis=2)  # brightness (HSV V) per pixel
        for s in self.slots:
            x, y, w, h = s.box
            zone_masked = masked[y: y + h, x: x + w]
            valid = ~zone_masked
            if valid.mean() < cfg.min_valid_pixel_fraction:
                self.occluded[s.id] += 1
                continue  # mostly hidden by a person this frame: no vote
            changed = (diff[y: y + h, x: x + w] > cfg.zone_diff_threshold) & valid
            changed_frac = changed.sum() / valid.sum()
            present = bool(changed_frac < cfg.zone_changed_fraction) if self.ref_has_equipment \
                else bool(changed_frac >= cfg.zone_changed_fraction)
            self.present_votes[s.id].append(present)
            if present and s.item_type in cfg.operability_types and s.indicator:
                ix, iy, iw, ih = s.indicator
                if masked[iy: iy + ih, ix: ix + iw].mean() < 0.3:
                    lamp = np.sort(value[iy: iy + ih, ix: ix + iw].ravel())
                    top = lamp[int(len(lamp) * 0.75):]  # brightest quarter: robust to blur at low resolution
                    self.led_votes[s.id].append(bool(top.mean() >= cfg.led_brightness_threshold))

    def results(self) -> list[SlotResult]:
        out: list[SlotResult] = []
        for s in self.slots:
            votes = self.present_votes[s.id]
            ratio = sum(votes) / len(votes) if votes else 0.0
            present = ratio >= 0.5 and bool(votes)
            if self.ref_has_equipment and not votes and self.occluded[s.id] > 0:
                # A person covers the item in every frame (e.g. someone seated on a chair): it is there, but unchecked.
                present, ratio = True, 1.0
            led = self.led_votes[s.id]
            led_ratio = sum(led) / len(led) if led else None
            if s.item_type not in self.cfg.operability_types:
                op = "not_checked"
            elif not present:
                op = "absent"
            elif led_ratio is None:
                op = "unknown"
            else:
                op = "operable" if led_ratio >= self.cfg.operable_vote_fraction else "not_operable"
            out.append(SlotResult(s.id, s.item_type, present, round(ratio, 3), len(votes), op,
                                  None if led_ratio is None else round(led_ratio, 3)))
        return out


def summarise(results: list[SlotResult]) -> tuple[dict[str, int], dict[str, int]]:
    detected = Counter(r.item_type for r in results if r.present)
    not_op = Counter(r.item_type for r in results if r.operability == "not_operable")
    return dict(detected), dict(not_op)
