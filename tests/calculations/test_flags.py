"""
Flags and the health score.

| metric         | value  | threshold     | result |
|----------------|--------|---------------|--------|
| current ratio  | 1.5    | >= 1.0        | met    |
| debt to equity | 0.5    | <= 2.0        | met    |
| net margin     | 8.4%   | > 10 (%)      | flag   |
| ROE            | 21%    | >= 21 (%)     | met (equal counts for >=) |
| ROE            | 21%    | > 21 (%)      | flag (equal does not count for >) |
Score with the first four thresholds: 3 met of 4 = 7.5 out of 10.
"""

from fractions import Fraction as F

from intelligence.flags import evaluate
from intelligence.ratios import Metric


def _m(key, unit, value):
    return Metric(key, key, unit, "", value=value)


METRICS = [_m("current_ratio", "x", F("1.5")), _m("debt_to_equity", "x", F("0.5")),
           _m("net_margin", "pct", F("0.084")), _m("roe", "pct", F("0.21")),
           Metric("quick_ratio", "Quick ratio", "x", "", missing=["Stock-in-trade (inventory)"])]


def _t(metric, op, value):
    return {"metric": metric, "op": op, "value": value, "rationale": "why"}


def test_score_and_flags():
    h = evaluate(METRICS, [_t("current_ratio", ">=", "1.0"), _t("debt_to_equity", "<=", "2.0"),
                           _t("net_margin", ">", "10"), _t("roe", ">=", "21")])
    assert [f.passed for f in h.flags] == [True, True, False, True]
    assert (h.passed, h.evaluated, h.score) == (3, 4, F("7.5"))


def test_equality_at_a_strict_threshold_is_flagged():
    h = evaluate(METRICS, [_t("roe", ">", "21")])
    assert h.flags[0].passed is False and h.score == 0


def test_uncomputed_metrics_are_not_evaluated():
    h = evaluate(METRICS, [_t("quick_ratio", ">=", "1"), _t("interest_coverage", ">=", "2")])
    assert h.evaluated == 0 and h.score is None and h.flags == []
