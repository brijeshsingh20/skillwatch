"""Accuracy evaluation on a labelled, randomised synthetic set. Writes docs/ACCURACY.md.

Usage (project root):  python -m scripts.evaluate [--n 40] [--seed 2026] [--out docs/ACCURACY.md]

For each generated clip we know the true headcount, which equipment is present, which machines are dead, the
camera quality, and what was claimed. We run the real pipeline and the real comparison/alert rules, then score:
  * headcount error (MAE, bias),
  * four alert types as binary classifiers (confusion table, precision, recall, FP/FN counts),
  * per-slot equipment presence and per-machine operability.
Both the normal and low-bandwidth profiles are scored, so the accuracy cost of low-bandwidth mode is visible.
"""
import argparse
import csv
import json
import logging
import random
import shutil
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from backend.app.services.comparison import DetectionSummary, Tolerance, compare, evaluate_rules
from scripts.generate_demo_footage import generate_centre
from scripts.metrics import Confusion, bias, mae, num, pct, pr_with_ci
from vision.pipeline import analyse_centre

log = logging.getLogger("evaluate")
ALERT_TYPES = ["attendance_mismatch", "equipment_missing", "equipment_not_operable", "low_quality"]
TOL = Tolerance()


def make_scenarios(n: int, seed: int) -> list[dict]:
    """Randomised labelled scenarios. Seeded, so the same command always gives the same set."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        chairs, benches, machines = rng.randint(6, 30), rng.randint(2, 6), rng.randint(1, 3)
        present = {"chair": chairs, "workbench": benches, "machine": machines}
        if rng.random() < 0.35:
            present["chair"] = chairs - max(1, int(chairs * rng.uniform(0.1, 0.4)))
        if rng.random() < 0.30:
            present["workbench"] = benches - 1
        if rng.random() < 0.30:
            present["machine"] = machines - 1
        not_operable = {"machine": 1} if present["machine"] and rng.random() < 0.30 else {}
        true_count = rng.randint(3, 30)
        r = rng.random()
        if r < 0.50:
            claimed = max(0, true_count + rng.randint(-1, 1))             # honest
        elif r < 0.65:
            gap = int(TOL.allowed(true_count)) + rng.choice([-1, 0, 1, 2])   # borderline
            claimed = max(0, true_count + rng.choice([-1, 1]) * max(0, gap))
        else:
            claimed = int(true_count * rng.uniform(1.3, 2.2)) + 1          # inflated
        out.append({
            "code": f"EV{i:03d}", "name": f"Eval {i}", "district": "-", "state": "-", "latitude": 0.0, "longitude": 0.0,
            "capacity": 60, "camera_profile": "poor" if rng.random() < 0.30 else "good",
            "sanctioned": {"chair": chairs, "workbench": benches, "machine": machines},
            "present": present, "not_operable": not_operable, "true_count": true_count, "claimed_count": claimed,
            "expected_alerts": [], "still_fraction": 0.3 if rng.random() < 0.25 else 0.0,
        })
    return out


def truth_alerts(sc: dict) -> set[str]:
    """Alerts a perfect observer would raise, using the very same comparison and rule code."""
    poor = sc["camera_profile"] == "poor"
    det = DetectionSummary(sc["true_count"], sc["present"], sc["not_operable"], 1.0, 0.75 if poor else 1.0, poor)
    comp = compare(det, sc["claimed_count"], sc["sanctioned"], TOL)
    return {a.alert_type.value for a in evaluate_rules(comp, det)}


def predicted_alerts(res, sc: dict) -> set[str]:
    det = DetectionSummary(res.estimated_count, res.items_detected, res.items_not_operable, res.confidence,
                           res.frame_quality, res.low_quality)
    return {a.alert_type.value for a in evaluate_rules(compare(det, sc["claimed_count"], sc["sanctioned"], TOL), det)}


def slot_truth(sc: dict) -> tuple[dict[str, bool], dict[str, bool]]:
    """(slot_id -> truly present, machine slot_id -> truly operable) for slots that exist in the layout."""
    present, operable = {}, {}
    for kind, quantity in sc["sanctioned"].items():
        have = sc["present"].get(kind, 0)
        dead = sc["not_operable"].get(kind, 0)
        for idx in range(quantity):
            present[f"{kind}-{idx + 1}"] = idx < have
            if kind == "machine" and idx < have:
                operable[f"{kind}-{idx + 1}"] = idx < have - dead
    return present, operable


def score_profile(scenarios: list[dict], root: Path, profile: str) -> dict:
    rows, alerts = [], {t: Confusion() for t in ALERT_TYPES}
    slots, ops = Confusion(), Confusion()
    for sc in scenarios:
        res = analyse_centre(sc["code"], root, profile)
        pred, truth = predicted_alerts(res, sc), truth_alerts(sc)
        for t in ALERT_TYPES:
            alerts[t].add(t in pred, t in truth)
        p_truth, o_truth = slot_truth(sc)
        for sr in res.slot_results:
            slots.add(sr.present, p_truth[sr.slot_id])
            if sr.slot_id in o_truth and p_truth[sr.slot_id]:
                ops.add(sr.operability == "not_operable", not o_truth[sr.slot_id])  # positive class = "not operable"
        rows.append({
            "code": sc["code"], "profile": profile, "true_count": sc["true_count"], "estimated": res.estimated_count,
            "error": res.estimated_count - sc["true_count"], "camera": sc["camera_profile"], "still": sc["still_fraction"],
            "claimed": sc["claimed_count"], "truth_alerts": "|".join(sorted(truth)), "pred_alerts": "|".join(sorted(pred)),
            "confidence": res.confidence, "seconds": res.processing_seconds, "thumb_bytes": res.thumb_bytes,
        })
    return {"rows": rows, "alerts": alerts, "slots": slots, "ops": ops}


def bucket(rows: list[dict], key) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        out[key(r)].append(r["error"])
    return out


def crowd(r: dict) -> str:
    return "3-10 people" if r["true_count"] <= 10 else "11-20 people" if r["true_count"] <= 20 else "21-30 people"


def render(n: int, seed: int, results: dict[str, dict]) -> str:
    L: list[str] = []
    normal, low = results["normal"], results["lowbw"]
    L += ["# Accuracy report", "",
          f"Generated by `python -m scripts.evaluate --n {n} --seed {seed}` on **{date.today().isoformat()}**. "
          f"{n} labelled synthetic clips (24 s each), scored with the real pipeline and the real alert rules.", "",
          "> **Read this first.** The footage is synthetic, drawn by code written alongside the detector, with flat "
          "backgrounds and uniformly coloured people. These numbers show that the pipeline works and where it breaks "
          "on easy data. They are an upper bound, not a prediction for real rooms. Real accuracy must be measured on "
          "real, labelled footage from the target centres before anyone acts on an alert.", ""]

    L += ["## 1. Headcount (people counting)", "",
          "Estimated minus true headcount, per clip. Positive = camera saw more than were present.", "",
          "| Profile | Clips | MAE (people) | Bias | Exact | Within 1 | Worst error |", "|---|---|---|---|---|---|---|"]
    for name, label in (("normal", "Normal (640 px, every 2 s)"), ("lowbw", "Low-bandwidth (320 px, every 4 s, at least 8 frames)")):
        errs = [r["error"] for r in results[name]["rows"]]
        L.append(f"| {label} | {len(errs)} | {num(mae(errs))} | {num(bias(errs))} | {pct(sum(e == 0 for e in errs) / len(errs))} | "
                 f"{pct(sum(abs(e) <= 1 for e in errs) / len(errs))} | {max(errs, key=abs):+d} |")
    L += ["", "### Where headcount errors come from (normal profile)", "",
          "| Condition | Clips | MAE | Bias |", "|---|---|---|---|"]
    rows = normal["rows"]
    for title, key in (("Crowd size", crowd), ("Camera", lambda r: f"{r['camera']} camera"),
                       ("Seated or still people", lambda r: "30% of people stand still" if r["still"] else "everyone moving")):
        for k, errs in sorted(bucket(rows, key).items()):
            L.append(f"| {title}: {k} | {len(errs)} | {num(mae(errs))} | {num(bias(errs))} |")

    L += ["", "## 2. Alerts as classifiers", "",
          "Ground truth = the alerts a perfect observer would raise from the true headcount and true equipment, using "
          "the same tolerance (max(2, 15% of claimed)) and rules. **FP** = alert raised that should not be (wasted officer time). "
          "**FN** = alert missed (a real problem not flagged). Brackets show a 95% Wilson interval, wide because n is small.", ""]
    for name, label in (("normal", "Normal profile"), ("lowbw", "Low-bandwidth profile")):
        L += [f"### {label}", "", "| Alert | TP | FP | FN | TN | Precision | Recall |", "|---|---|---|---|---|---|---|"]
        for t in ALERT_TYPES:
            c = results[name]["alerts"][t]
            p, r = pr_with_ci(c)
            L.append(f"| {t} | {c.tp} | {c.fp} | {c.fn} | {c.tn} | {p} | {r} |")
        L.append("")

    L += ["## 3. Equipment detail", "",
          "| Profile | Check | TP | FP | FN | TN | Precision | Recall |", "|---|---|---|---|---|---|---|---|"]
    for name in ("normal", "lowbw"):
        for label, c in (("Slot present (apparent presence)", results[name]["slots"]),
                         ("Machine not operable (apparent operability)", results[name]["ops"])):
            p, r = pr_with_ci(c)
            L.append(f"| {name} | {label} | {c.tp} | {c.fp} | {c.fn} | {c.tn} | {p} | {r} |")

    worst = sorted(rows, key=lambda r: -abs(r["error"]))[:5]
    L += ["", "## 4. Five worst headcount errors (normal profile)", "",
          "| Clip | True | Estimated | Camera | Still people |", "|---|---|---|---|---|"]
    L += [f"| {r['code']} | {r['true_count']} | {r['estimated']} | {r['camera']} | {'yes' if r['still'] else 'no'} |" for r in worst]

    t_n = sum(r["seconds"] for r in rows) / len(rows)
    t_l = sum(r["seconds"] for r in low["rows"]) / len(low["rows"])
    b_l = sum(r["thumb_bytes"] for r in low["rows"]) / len(low["rows"]) / 1024
    L += ["", "## 5. Cost of low-bandwidth mode", "",
          f"Average analysis time per clip on the development PC: {t_n:.2f} s (normal) vs {t_l:.2f} s (low-bandwidth). "
          f"Average low-bandwidth thumbnail: {b_l:.1f} KB. Compare the two profiles in sections 1-3 for the accuracy cost.", "",
          "## 6. Known limits (honest list)", "",
          "- **Synthetic data.** Real rooms have clutter, shadows, glare, partial occlusion, varied clothing and lighting changes. None of that is tested here.",
          "- **The motion counter cannot see people who stand still.** They are absorbed into the median background. The still-people rows above measure this undercount. For real footage use the YOLO backend (`VISION_PERSON_DETECTOR=yolo`), which does not have this weakness but was **not evaluated here** (no network or weights in the build environment).",
          "- **Crowds merge.** Touching people form one blob; an area-based split guesses how many. Error grows with crowd size (see the crowd table).",
          "- **Equipment checks need a fixed camera and an empty-room reference image.** If the camera moves, every slot can read wrong. Presence and operability are visual proxies, labelled *apparent*, never *verified*.",
          "- **Operability only means a lit indicator lamp.** A machine can be powered and broken, or unpowered and fine.",
          "- **Thresholds were tuned on similar synthetic scenes.** The quality threshold and zone-difference threshold need recalibration per camera.",
          "- **Small sample.** With this many clips, precision and recall have wide intervals. Rare cases (for example a missing workbench on a poor camera) have only a handful of examples.",
          "- **Ground truth for alerts is derived from the same rules**, so this measures perception error, not whether the rules themselves are the right policy.", "",
          "## 7. Recommended use", "",
          "Treat alerts as prompts for a human to look at the annotated frame, never as findings. Run a pilot on real, hand-labelled "
          "footage from 2-3 centres, re-run this script against it, and set the tolerance and thresholds from those results.", ""]
    return "\n".join(L)


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", default="docs/ACCURACY.md")
    parser.add_argument("--keep", action="store_true", help="keep generated eval clips under data/eval")
    parser.add_argument("--stage", choices=["all", "generate", "score"], default="all",
                        help="generate clips only, or score existing clips (needs --keep for the split)")
    args = parser.parse_args()

    scenarios = make_scenarios(args.n, args.seed)
    keep = args.keep or args.stage != "all"
    root = Path("data/eval") if keep else Path(tempfile.mkdtemp(prefix="skillwatch_eval_"))
    report = ""
    results: dict[str, dict] = {}
    try:
        if args.stage in ("all", "generate"):
            for i, sc in enumerate(scenarios, 1):
                if not (root / "videos" / f"{sc['code']}.mp4").exists():  # resumable
                    generate_centre(sc, root, duration_s=24, fps=8, seed=args.seed, still_fraction=sc["still_fraction"])
                if i % 10 == 0:
                    log.info("Generated %d/%d clips", i, len(scenarios))
        if args.stage in ("all", "score"):
            results = {p: score_profile(scenarios, root, p) for p in ("normal", "lowbw")}
            report = render(args.n, args.seed, results)
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
    if args.stage == "generate":
        log.info("Clips ready in %s. Now run with --stage score", root)
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    all_rows = results["normal"]["rows"] + results["lowbw"]["rows"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    log.info("Wrote %s and %s", out, csv_path)
    print(report)


if __name__ == "__main__":
    main()
