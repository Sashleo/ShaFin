"""
DuPont: net margin x asset turnover x equity multiplier multiplies back to ROE exactly.

| component          | working              | value  |
|--------------------|----------------------|--------|
| net margin         | 84,000 / 1,000,000   | 0.084  |
| asset turnover     | 1,000,000 / 800,000  | 1.25   |
| equity multiplier  | 800,000 / 400,000    | 2      |
| product            | 0.084 x 1.25 x 2     | 0.21   |
| ROE directly       | 84,000 / 400,000     | 0.21   |
"""

import random
from fractions import Fraction as F

from intelligence.ratios import compute_dupont, compute_ratios

CUR = {"profit_after_tax": 84_000, "revenue": 1_000_000, "total_assets": 800_000,
       "total_equity": 400_000}


def test_hand_computed_components():
    d = compute_dupont(CUR)
    assert (d.net_margin, d.asset_turnover, d.equity_multiplier) == (F("0.084"), F("1.25"), F(2))
    assert d.roe == F("0.21")


def test_multiplies_back_to_roe_exactly():
    roe = {m.key: m.value for m in compute_ratios(CUR, {})}["roe"]
    assert compute_dupont(CUR).roe == roe


def test_multiplies_back_for_any_figures():
    rng = random.Random(20261028)
    for _ in range(500):
        cur = {"profit_after_tax": rng.randint(-10**12, 10**12),
               "revenue": rng.randint(1, 10**13), "total_assets": rng.randint(1, 10**13),
               "total_equity": rng.choice([-1, 1]) * rng.randint(1, 10**13)}
        d = compute_dupont(cur)
        assert d.roe == F(cur["profit_after_tax"], cur["total_equity"])


def test_missing_input_is_named():
    d = compute_dupont({"revenue": 1})
    assert d.roe is None and "Total equity" in d.missing


def test_zero_denominator_gives_no_roe():
    assert compute_dupont(dict(CUR, total_assets=0)).roe is None
