"""Comparison engine and alert rules. Pure functions: no database, easy to test and to explain.

All equipment findings are *apparent* (visual proxies), never verified facts.
"""
from dataclasses import dataclass, field

from backend.app.enums import AlertType, Severity


@dataclass(frozen=True)
class Tolerance:
    """Allowed gap between claimed and estimated attendance = max(minimum, pct x claimed)."""
    pct: float = 0.15
    minimum: int = 2

    def allowed(self, claimed: int) -> float:
        return max(float(self.minimum), self.pct * claimed)


@dataclass(frozen=True)
class DetectionSummary:
    """What the vision pipeline reports for one observation."""
    estimated_count: int
    items_detected: dict[str, int]
    items_not_operable: dict[str, int]
    confidence: float
    frame_quality: float
    low_quality: bool
    frame_ref: str | None = None


@dataclass
class Comparison:
    estimated_count: int
    claimed_count: int | None
    difference: int | None            # estimated - claimed (negative = claimed more than seen)
    allowed_gap: float | None
    attendance_mismatch: bool
    discrepancy_score: float          # 0 (consistent) .. 1 (claim wildly off)
    items_detected: dict[str, int]
    items_missing: dict[str, int]
    items_not_operable: dict[str, int]
    sanctioned: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AlertCandidate:
    alert_type: AlertType
    severity: Severity
    message: str


def compare(detection: DetectionSummary, claimed: int | None, sanctioned: dict[str, int],
            tolerance: Tolerance = Tolerance()) -> Comparison:
    missing = {t: q - detection.items_detected.get(t, 0) for t, q in sanctioned.items()
               if q > detection.items_detected.get(t, 0)}
    diff = allowed = None
    mismatch, score = False, 0.0
    if claimed is not None:
        diff = detection.estimated_count - claimed
        allowed = tolerance.allowed(claimed)
        excess = max(0.0, abs(diff) - allowed)
        mismatch = excess > 0
        score = round(min(1.0, excess / max(claimed, detection.estimated_count, 1)), 3)
    return Comparison(detection.estimated_count, claimed, diff, allowed, mismatch, score,
                      dict(detection.items_detected), missing, dict(detection.items_not_operable), dict(sanctioned))


def _attendance_severity(score: float) -> Severity:
    return Severity.HIGH if score >= 0.5 else Severity.MEDIUM if score >= 0.25 else Severity.LOW


def _missing_severity(missing: dict[str, int], sanctioned: dict[str, int]) -> Severity:
    worst = max(q / sanctioned[t] for t, q in missing.items())  # worst per-type shortfall
    return Severity.HIGH if worst >= 0.4 else Severity.MEDIUM if worst >= 0.15 else Severity.LOW


def evaluate_rules(comp: Comparison, detection: DetectionSummary) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []

    if comp.attendance_mismatch:
        severity = _attendance_severity(comp.discrepancy_score)
        note = ""
        if detection.low_quality and severity is Severity.HIGH:
            severity, note = Severity.MEDIUM, " Image quality is low, so verify manually before acting."
        direction = ("fewer people than claimed (possible inflated attendance)" if comp.difference < 0
                     else "more people than claimed (possible under-reporting)")
        out.append(AlertCandidate(
            AlertType.ATTENDANCE_MISMATCH, severity,
            f"Claimed {comp.claimed_count} present; camera estimates about {comp.estimated_count} "
            f"({direction}). Allowed gap +/-{comp.allowed_gap:.1f}.{note}"))

    if comp.items_missing:
        parts = ", ".join(f"{q} of {comp.sanctioned[t]} {t}" for t, q in sorted(comp.items_missing.items()))
        out.append(AlertCandidate(
            AlertType.EQUIPMENT_MISSING, _missing_severity(comp.items_missing, comp.sanctioned),
            f"Apparently missing versus sanctioned inventory: {parts}. (Apparent presence, not verified.)"))

    if comp.items_not_operable:
        parts = ", ".join(f"{q} {t}" for t, q in sorted(comp.items_not_operable.items()))
        total_present = sum(comp.items_detected.get(t, 0) for t in comp.items_not_operable) or 1
        share = sum(comp.items_not_operable.values()) / total_present
        out.append(AlertCandidate(
            AlertType.EQUIPMENT_NOT_OPERABLE, Severity.HIGH if share >= 0.5 else Severity.MEDIUM,
            f"Apparently not operable (no power indicator seen): {parts}. (Apparent operability, not verified.)"))

    if detection.low_quality:
        severity = Severity.MEDIUM if detection.frame_quality < 0.5 else Severity.LOW
        out.append(AlertCandidate(
            AlertType.LOW_QUALITY, severity,
            f"Camera image quality is low ({detection.frame_quality:.2f}); counts and equipment checks are less reliable."))
    return out
