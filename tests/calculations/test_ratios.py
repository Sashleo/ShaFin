"""
Ratios for manufacturers and non-manufacturers. One fictional company, figures in
whole rupees, every value hand-computed:

| figure                    | current   | prior   |
|---------------------------|-----------|---------|
| revenue                   | 1,000,000 | 800,000 |
| cost of sales             |   600,000 |         |
| gross profit              |   400,000 |         |
| operating profit (EBIT)   |   150,000 |         |
| finance cost              |    30,000 |         |
| profit after tax          |    84,000 |  60,000 |
| total assets              |   800,000 |         |
| current assets            |   300,000 |         |
| inventory                 |   100,000 |         |
| trade receivables         |    80,000 |         |
| current liabilities       |   200,000 |         |
| trade payables            |    90,000 |         |
| short-term borrowings     |    60,000 |         |
| long-term borrowings      |   140,000 |         |
| total liabilities         |   400,000 |         |
| total equity              |   400,000 |         |
| shares outstanding        |    10,000 |         |
| cash from operations      |   130,000 |         |
| capital expenditure       |    70,000 |         |

| metric                | working                          | value          |
|-----------------------|----------------------------------|----------------|
| gross margin          | 400,000 / 1,000,000              | 0.40           |
| operating margin      | 150,000 / 1,000,000              | 0.15           |
| net margin            | 84,000 / 1,000,000               | 0.084          |
| ROE                   | 84,000 / 400,000                 | 0.21           |
| ROA                   | 84,000 / 800,000                 | 0.105          |
| current ratio         | 300,000 / 200,000                | 1.5            |
| quick ratio           | (300,000 - 100,000) / 200,000    | 1.0            |
| debt to equity        | (60,000 + 140,000) / 400,000     | 0.5            |
| liabilities to assets | 400,000 / 800,000                | 0.5            |
| equity multiplier     | 800,000 / 400,000                | 2              |
| interest coverage     | 150,000 / 30,000                 | 5              |
| asset turnover        | 1,000,000 / 800,000              | 1.25           |
| days receivable       | 80,000 / 1,000,000 x 365         | 29.2           |
| days inventory        | 100,000 / 600,000 x 365          | 365/6 = 60.83  |
| days payable          | 90,000 / 600,000 x 365           | 54.75          |
| free cash flow        | 130,000 - 70,000                 | 60,000         |
| EPS                   | 84,000 / 10,000                  | 8.4            |
| revenue growth        | (1,000,000 - 800,000) / 800,000  | 0.25           |
| PAT growth            | (84,000 - 60,000) / 60,000       | 0.4            |
"""

from fractions import Fraction as F

import pytest

from intelligence.display import fmt
from intelligence.ratios import compute_ratios

CUR = {
    "revenue": 1_000_000, "cost_of_sales": 600_000, "gross_profit": 400_000,
    "operating_profit": 150_000, "finance_cost": 30_000, "profit_after_tax": 84_000,
    "total_assets": 800_000, "current_assets": 300_000, "inventory": 100_000,
    "trade_receivables": 80_000, "current_liabilities": 200_000, "trade_payables": 90_000,
    "short_term_borrowings": 60_000, "long_term_borrowings": 140_000,
    "total_liabilities": 400_000, "total_equity": 400_000, "shares_outstanding": 10_000,
    "cash_from_operations": 130_000, "capital_expenditure": 70_000,
}
PRIOR = {"revenue": 800_000, "profit_after_tax": 60_000}

EXPECTED = {
    "gross_margin": F("0.40"),
    "operating_margin": F("0.15"),
    "net_margin": F("0.084"),
    "roe": F("0.21"),
    "roa": F("0.105"),
    "current_ratio": F("1.5"),
    "quick_ratio": F("1.0"),
    "debt_to_equity": F("0.5"),
    "liabilities_to_assets": F("0.5"),
    "equity_multiplier": F(2),
    "interest_coverage": F(5),
    "asset_turnover": F("1.25"),
    "days_receivable": F("29.2"),
    "days_inventory": F(365, 6),
    "days_payable": F("54.75"),
    "free_cash_flow": F(60_000),
    "eps": F("8.4"),
    "revenue_growth": F("0.25"),
    "pat_growth": F("0.4"),
}


def _metrics(cur=CUR, prior=PRIOR):
    return {m.key: m for m in compute_ratios(cur, prior)}


@pytest.mark.parametrize("key", EXPECTED)
def test_hand_computed_value(key):
    m = _metrics()[key]
    assert m.value == EXPECTED[key], f"{key}: {m.value} != {EXPECTED[key]}"


def test_every_ratio_has_a_vector():
    assert set(_metrics()) == set(EXPECTED)


def test_display_rounding():
    m = _metrics()
    assert fmt(m["days_inventory"].value, "days") == "60.8 days"
    assert fmt(m["net_margin"].value, "pct") == "8.40%"
    assert fmt(m["eps"].value, "per_share") == "PKR 8.40"


def test_a_missing_input_is_named_not_guessed():
    cur = dict(CUR)
    del cur["inventory"]
    m = _metrics(cur)
    assert m["quick_ratio"].value is None
    assert m["quick_ratio"].missing == ["Stock-in-trade (inventory)"]
    assert m["days_inventory"].missing == ["Stock-in-trade (inventory)"]
    assert m["current_ratio"].value == F("1.5")          # unaffected


def test_zero_denominator_is_not_defined_not_zero():
    cur = dict(CUR, finance_cost=0, revenue=0)
    m = _metrics(cur)
    assert m["interest_coverage"].value is None
    assert m["interest_coverage"].note == "Not defined: finance cost is zero."
    assert m["gross_margin"].value is None and "Not defined" in m["gross_margin"].note


def test_growth_from_a_loss_is_not_defined():
    m = _metrics(prior={"revenue": 800_000, "profit_after_tax": -10_000})
    assert m["pat_growth"].value is None and "loss" in m["pat_growth"].note


def test_growth_needs_the_prior_year():
    m = _metrics(prior={})
    assert m["revenue_growth"].missing == ["prior revenue"]


def test_negative_profit_gives_negative_margins():
    m = _metrics(dict(CUR, profit_after_tax=-50_000))
    assert m["net_margin"].value == F("-0.05")
    assert m["roe"].value == F("-0.125")
