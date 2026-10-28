"""
Statement checks: each identity holds within one unit of the reporting unit.

| check                                  | left                | right                         | diff |
|----------------------------------------|---------------------|-------------------------------|------|
| total assets = liabilities + equity    | 800,000             | 400,000 + 400,000             | 0    |
| gross profit = revenue - cost of sales | 400,000             | 1,000,000 - 600,000           | 0    |
| PBT = operating profit - finance cost  | 120,000             | 150,000 - 30,000              | 0    |
| PAT = PBT - taxation                   | 84,000              | 120,000 - 36,000              | 0    |
| CFO + CFI + CFF = change in cash       | 130,000 - 90,000    | 50,000 - 40,000               | 0    |
|                                        |  - 30,000 = 10,000  |   = 10,000                    |      |
With figures entered in thousands the tolerance is 1,000 rupees: a difference of 1,000
passes and 1,001 does not.
"""

import pytest

from intelligence.checks import run_checks

CUR = {"total_assets": 800_000, "total_liabilities": 400_000, "total_equity": 400_000,
       "gross_profit": 400_000, "revenue": 1_000_000, "cost_of_sales": 600_000,
       "profit_before_tax": 120_000, "operating_profit": 150_000, "finance_cost": 30_000,
       "profit_after_tax": 84_000, "tax_expense": 36_000, "cash_from_operations": 130_000,
       "cash_from_investing": -90_000, "cash_from_financing": -30_000, "cash": 50_000}
PRIOR = {"cash": 40_000}


def test_every_identity_holds():
    checks = run_checks("manufacturer", CUR, PRIOR, tolerance=1_000)
    assert len(checks) == 5
    assert all(c.passed and c.difference == 0 for c in checks), [(c.label, c.difference) for c in checks]


@pytest.mark.parametrize("off, passed", [(1_000, True), (1_001, False), (-1_000, True), (-1_001, False)])
def test_tolerance_is_one_reporting_unit(off, passed):
    c = run_checks("manufacturer", dict(CUR, total_assets=800_000 + off), PRIOR, tolerance=1_000)[0]
    assert c.difference == off and c.passed is passed


def test_cash_flow_check_needs_last_years_cash():
    c = run_checks("manufacturer", CUR, {}, tolerance=1)[-1]
    assert c.passed is None and "Cash and bank balances (prior)" in c.missing


def test_bank_identities():
    cur = {"net_markup_income": 500, "markup_earned": 1_200, "markup_expensed": 700,
           "net_advances": 3_760, "gross_advances": 4_000, "advance_provisions": 240,
           "profit_before_tax": 300, "non_markup_income": 200, "operating_expenses": 350,
           "provisions": 50}
    checks = run_checks("bank", cur, {}, tolerance=1)
    assert [c.passed for c in checks] == [True, True, True]
    off = run_checks("bank", dict(cur, net_advances=3_700), {}, tolerance=1)[1]
    assert off.passed is False and off.difference == -60
