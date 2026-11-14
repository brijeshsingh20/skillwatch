"""Small, dependency-free evaluation helpers."""
import math
from dataclasses import dataclass


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, predicted: bool, actual: bool) -> None:
        if predicted and actual:
            self.tp += 1
        elif predicted and not actual:
            self.fp += 1
        elif actual:
            self.fn += 1
        else:
            self.tn += 1

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p is not None and r is not None and (p + r) else None

    @property
    def accuracy(self) -> float | None:
        return (self.tp + self.tn) / self.total if self.total else None


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; honest about small samples."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mae(errors: list[float]) -> float | None:
    return sum(abs(e) for e in errors) / len(errors) if errors else None


def bias(errors: list[float]) -> float | None:
    return sum(errors) / len(errors) if errors else None


def pct(value: float | None, digits: int = 0) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def pr_with_ci(c: Confusion) -> tuple[str, str]:
    """Precision and recall with 95% intervals, as display strings."""
    def fmt(k: int, n: int, val: float | None) -> str:
        ci = wilson(k, n)
        return "n/a" if val is None or ci is None else f"{val * 100:.0f}% ({ci[0] * 100:.0f}-{ci[1] * 100:.0f})"
    return fmt(c.tp, c.tp + c.fp, c.precision), fmt(c.tp, c.tp + c.fn, c.recall)
