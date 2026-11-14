"""Compliance score (0-100) from one comparison. Weights: attendance 40, inventory 40, operability 20."""
from backend.app.services.comparison import Comparison


def compliance_score(comp: Comparison) -> int:
    if comp.claimed_count is None:
        attendance = 1.0  # nothing claimed, nothing to contradict
    elif comp.attendance_mismatch:
        attendance = max(0.0, 1.0 - abs(comp.difference or 0) / max(comp.claimed_count, comp.estimated_count, 1))
    else:
        attendance = 1.0

    # Average shortfall per item type, so one missing machine counts as much as missing chairs of equal share.
    shortfalls = [comp.items_missing.get(t, 0) / q for t, q in comp.sanctioned.items() if q > 0]
    inventory = 1.0 if not shortfalls else 1.0 - sum(shortfalls) / len(shortfalls)

    checked_present = sum(comp.items_detected.get(t, 0) for t in comp.items_not_operable)
    broken = sum(comp.items_not_operable.values())
    operability = 1.0 if checked_present == 0 else 1.0 - broken / checked_present

    return round(100 * (0.4 * attendance + 0.4 * inventory + 0.2 * operability))
