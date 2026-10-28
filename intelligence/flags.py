"""
intelligence/flags.py - Flags from the owner's threshold table, and the health score.

Each threshold row (Settings -> Thresholds) names a metric, a comparison and a value,
with its rationale. A metric that is computed and fails its threshold is flagged.
The health score is the share of evaluated thresholds that pass, out of 10, with the
number evaluated shown beside it; with nothing evaluated there is no score.
Percentage thresholds are stored as percentages (11.5 means 11.5%).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from intelligence.units import parse_number

OPS = {
    ">=": lambda v, t: v >= t,
    ">": lambda v, t: v > t,
    "<=": lambda v, t: v <= t,
    "<": lambda v, t: v < t,
}


@dataclass
class Flag:
    metric: str
    label: str
    value: Fraction
    op: str
    threshold: str
    unit: str
    rationale: str
    passed: bool


@dataclass
class Health:
    score: Optional[Fraction]
    evaluated: int
    passed: int
    flags: list


def evaluate(metrics: list, thresholds: list[dict]) -> Health:
    """metrics: [Metric]; thresholds: rows with metric, op, value, rationale."""
    by_key = {m.key: m for m in metrics if m.computed}
    results = []
    for t in thresholds:
        m = by_key.get(t["metric"])
        if m is None:
            continue
        limit = parse_number(t["value"])
        if m.unit == "pct":
            limit /= 100
        results.append(Flag(m.key, m.label, m.value, t["op"], t["value"], m.unit,
                            t["rationale"], OPS[t["op"]](m.value, limit)))
    passed = sum(f.passed for f in results)
    score = Fraction(passed * 10, len(results)) if results else None
    return Health(score, len(results), passed, results)
