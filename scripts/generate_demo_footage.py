"""Synthesise demo footage, equipment layouts, empty-room references and ground truth.

Usage (project root):  python -m scripts.generate_demo_footage [--duration 40] [--fps 8]

Per centre this writes:
  data/videos/<code>.mp4            simulated camera clip (moving 'people', labelled equipment)
  data/layouts/<code>.json          equipment slots (the zones the pipeline checks)
  data/reference/<code>.png         empty-room reference captured through the same camera
  data/ground_truth/<code>.json     what is really in the room (for evaluation)
"""
import argparse
import json
import logging
import math
import random
from pathlib import Path

import cv2
import numpy as np

from scripts.scenario import SCENARIO, CentreScenario

log = logging.getLogger("footage")
W, H = 640, 480
PERSON_W, PERSON_H = 18, 43  # approximate drawn size (head + torso)
SHIRTS = [(200, 40, 40), (40, 80, 200), (200, 120, 20), (140, 40, 160), (20, 150, 160), (210, 190, 30)]


def build_layout(sanctioned: dict[str, int]) -> dict:
    """Fixed floor plan: workbenches along the top, chairs in the middle, machines along the bottom."""
    slots: list[dict] = []
    for i in range(sanctioned.get("workbench", 0)):
        slots.append({"id": f"workbench-{i+1}", "item_type": "workbench", "box": [15 + i * 100, 25, 90, 50]})
    for i in range(sanctioned.get("chair", 0)):
        col, row = i % 14, i // 14
        slots.append({"id": f"chair-{i+1}", "item_type": "chair", "box": [30 + col * 40, 150 + row * 45, 26, 26]})
    for i in range(sanctioned.get("machine", 0)):
        x, y = 20 + i * 90, 395
        slots.append({"id": f"machine-{i+1}", "item_type": "machine", "box": [x, y, 70, 70],
                      "indicator": [x + 54, y + 6, 10, 10]})
    return {"frame_size": [W, H], "slots": slots}


def base_floor() -> np.ndarray:
    rng = np.random.default_rng(7)  # fixed texture so reference and clips share the floor
    grad = np.linspace(145, 160, H, dtype=np.float32)[:, None, None]
    floor = np.repeat(np.repeat(grad, W, axis=1), 3, axis=2)
    floor += rng.normal(0, 2.0, (H, W, 1)).astype(np.float32)
    return np.clip(floor, 0, 255).astype(np.uint8)


def draw_slot(img: np.ndarray, slot: dict, powered: bool) -> None:
    x, y, w, h = slot["box"]
    kind = slot["item_type"]
    if kind == "chair":
        cv2.rectangle(img, (x, y), (x + w, y + h), (30, 60, 100), -1)
        cv2.rectangle(img, (x, y), (x + w, y + 7), (20, 40, 70), -1)
    elif kind == "workbench":
        cv2.rectangle(img, (x, y), (x + w, y + h), (70, 120, 170), -1)
        cv2.rectangle(img, (x, y), (x + w, y + h), (40, 80, 120), 2)
        cv2.putText(img, "BENCH", (x + 8, y + 31), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1, cv2.LINE_AA)
    else:
        cv2.rectangle(img, (x, y), (x + w, y + h), (110, 60, 50), -1)
        cv2.putText(img, "LATHE", (x + 6, y + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (240, 240, 240), 1, cv2.LINE_AA)
        ix, iy, iw, ih = slot["indicator"]
        led = (60, 230, 60) if powered else (70, 70, 70)
        cv2.circle(img, (ix + iw // 2, iy + ih // 2), 5, led, -1)


def draw_person(img: np.ndarray, cx: float, cy: float, shirt: tuple[int, int, int]) -> None:
    x, y = int(cx), int(cy)
    cv2.rectangle(img, (x - 9, y - 14), (x + 9, y + 14), shirt, -1)
    cv2.circle(img, (x, y - 22), 7, (150, 175, 205), -1)  # head (BGR skin tone)


def degrade(img: np.ndarray, profile: str, rng: np.random.Generator) -> np.ndarray:
    """Simulate camera quality. 'poor' = blur + noise + low contrast (rural/old CCTV)."""
    out = img.astype(np.float32)
    if profile == "poor":
        small = cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
        out = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32)
        out = (out - 128) * 0.72 + 128
        out += rng.normal(0, 5, out.shape)
    else:
        out += rng.normal(0, 2.5, out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def render_static(layout: dict, present: dict[str, int], not_operable: dict[str, int]) -> np.ndarray:
    """Room with only the equipment that is really present (first N slots of each type)."""
    img = base_floor()
    seen: dict[str, int] = {}
    for slot in layout["slots"]:
        kind = slot["item_type"]
        idx = seen.get(kind, 0)
        seen[kind] = idx + 1
        if idx >= present.get(kind, 0):
            continue  # equipment missing: slot left empty
        # the last N present machines are the unpowered ones
        dead_from = present.get(kind, 0) - not_operable.get(kind, 0)
        draw_slot(img, slot, powered=idx < dead_from)
    return img


def simulate_people(n: int, frames: int, fps: int, rng: random.Random,
                    still_fraction: float = 0.0) -> list[list[tuple[float, float, int]]]:
    """Random-waypoint walkers with simple separation. Returns per-frame (x, y, shirt_index).

    `still_fraction` of the people never move (e.g. seated trainees); the evaluation uses this to test the
    motion counter on a case it is known to find hard.
    """
    xmin, xmax, ymin, ymax = 25, W - 25, 120, 375
    pos = [[rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)] for _ in range(n)]
    goal = [[rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)] for _ in range(n)]
    speed = [rng.uniform(35, 70) for _ in range(n)]
    for i in range(int(round(n * still_fraction))):
        speed[i] = 0.0
        goal[i] = list(pos[i])
    track: list[list[tuple[float, float, int]]] = []
    for _ in range(frames):
        for i in range(n):
            dx, dy = goal[i][0] - pos[i][0], goal[i][1] - pos[i][1]
            dist = math.hypot(dx, dy)
            if speed[i] == 0:
                continue
            if dist < 6:
                goal[i] = [rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)]
                continue
            step = speed[i] / fps
            pos[i][0] += dx / dist * step
            pos[i][1] += dy / dist * step
        for i in range(n):  # keep walkers from fully overlapping
            for j in range(i + 1, n):
                ddx, ddy = pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]
                d = math.hypot(ddx, ddy)
                if d < 26:
                    push = (26 - d) / 2 + 0.5
                    ux, uy = (ddx / d, ddy / d) if d > 0 else (1.0, 0.0)
                    pos[i][0] += ux * push; pos[i][1] += uy * push
                    pos[j][0] -= ux * push; pos[j][1] -= uy * push
        for p in pos:
            p[0] = min(max(p[0], xmin), xmax)
            p[1] = min(max(p[1], ymin), ymax)
        track.append([(p[0], p[1], i % len(SHIRTS)) for i, p in enumerate(pos)])
    return track


def open_writer(path: Path, fps: int) -> cv2.VideoWriter:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open video writer for {path}")
    return writer


def generate_centre(sc: CentreScenario, root: Path, duration_s: int = 40, fps: int = 8, seed: int = 1,
                    still_fraction: float = 0.0) -> dict:
    code = sc["code"]
    for sub in ("videos", "layouts", "reference", "ground_truth"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    layout = build_layout(sc["sanctioned"])
    profile = sc["camera_profile"]
    nprng = np.random.default_rng(seed + sum(map(ord, code)))
    prng = random.Random(seed + sum(map(ord, code)))

    # Empty-room reference: average several degraded renders of the bare floor.
    bare = base_floor()
    ref = np.mean([degrade(bare, profile, nprng).astype(np.float32) for _ in range(12)], axis=0).astype(np.uint8)
    cv2.imwrite(str(root / "reference" / f"{code}.png"), ref)

    static = render_static(layout, sc["present"], sc["not_operable"])
    frames = duration_s * fps
    track = simulate_people(sc["true_count"], frames, fps, prng, still_fraction)
    video_path = root / "videos" / f"{code}.mp4"
    writer = open_writer(video_path, fps)
    try:
        for people in track:
            frame = static.copy()
            for x, y, s in sorted(people, key=lambda p: p[1]):  # back-to-front
                draw_person(frame, x, y, SHIRTS[s])
            writer.write(degrade(frame, profile, nprng))
    finally:
        writer.release()

    (root / "layouts" / f"{code}.json").write_text(json.dumps(layout, indent=2))
    missing = {k: v - sc["present"].get(k, 0) for k, v in sc["sanctioned"].items() if v > sc["present"].get(k, 0)}
    truth = {
        "centre_code": code, "video": f"videos/{code}.mp4", "fps": fps, "duration_s": duration_s,
        "camera_profile": profile, "still_fraction": still_fraction, "true_count": sc["true_count"], "claimed_count": sc["claimed_count"],
        "sanctioned": sc["sanctioned"], "present": sc["present"], "missing": missing,
        "not_operable": sc["not_operable"], "expected_alerts": sc["expected_alerts"],
    }
    (root / "ground_truth" / f"{code}.json").write_text(json.dumps(truth, indent=2))
    log.info("%s: %s (%.0f KB)", code, video_path.name, video_path.stat().st_size / 1024)
    return truth


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data")
    parser.add_argument("--duration", type=int, default=40)
    parser.add_argument("--fps", type=int, default=8)
    args = parser.parse_args()
    for sc in SCENARIO:
        generate_centre(sc, Path(args.out), args.duration, args.fps)
    log.info("Demo footage written to %s/", args.out)


if __name__ == "__main__":
    main()
