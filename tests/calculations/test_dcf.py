"""
DCF (free cash flow to the firm). Formulas: docs/CALCULATIONS.md.

Vector 1: two forecast years.
Facts: revenue 1,000,000; cash 50,000; short-term borrowings 60,000; long-term
borrowings 140,000; shares 10,000. Assumptions: risk-free 9%, beta 1.5, ERP 6%,
cost of debt 8%, tax 25%, debt weight 25%, revenue growth 10%, EBIT margin 20%,
D&A 5%, capex 6%, working capital 10% of the revenue increase, terminal growth 5%.

| step                 | working                                        | value         |
|----------------------|------------------------------------------------|---------------|
| Ke (CAPM)            | 0.09 + 1.5 x 0.06                              | 0.18          |
| WACC                 | 0.75 x 0.18 + 0.25 x 0.08 x (1 - 0.25)         | 0.15          |
| Revenue, year 1      | 1,000,000 x 1.10                               | 1,100,000     |
| EBIT, year 1         | 1,100,000 x 0.20                               | 220,000       |
| NOPAT, year 1        | 220,000 x 0.75                                 | 165,000       |
| D&A / capex, year 1  | 1,100,000 x 0.05 / x 0.06                      | 55,000/66,000 |
| delta NWC, year 1    | (1,100,000 - 1,000,000) x 0.10                 | 10,000        |
| FCFF, year 1         | 165,000 + 55,000 - 66,000 - 10,000             | 144,000       |
| Revenue, year 2      | 1,100,000 x 1.10                               | 1,210,000     |
| NOPAT, year 2        | 1,210,000 x 0.20 x 0.75                        | 181,500       |
| D&A / capex, year 2  | 60,500 / 72,600                                |               |
| delta NWC, year 2    | 110,000 x 0.10                                 | 11,000        |
| FCFF, year 2         | 181,500 + 60,500 - 72,600 - 11,000             | 158,400       |
| PV year 1            | 144,000 / 1.15            = 2,880,000 / 23     | 125,217.39    |
| PV year 2            | 158,400 / 1.3225          = 63,360,000 / 529   | 119,773.16    |
| Terminal value       | 158,400 x 1.05 / (0.15 - 0.05)                 | 1,663,200     |
| PV of TV             | 1,663,200 / 1.3225        = 665,280,000 / 529  | 1,257,618.15  |
| EV                   | (66,240,000 + 63,360,000 + 665,280,000) / 529  |               |
|                      | = 794,880,000 / 529                            | 1,502,608.70  |
| net debt             | 60,000 + 140,000 - 50,000                      | 150,000       |
| equity               | 794,880,000/529 - 150,000 = 715,530,000 / 529  | 1,352,608.70  |
| per share            | 715,530,000 / 529 / 10,000 = 3,111 / 23        | 135.26        |

Vector 2: one forecast year, for the sensitivity grid. FCFF_1 = 100,000, no net debt,
1,000 shares. With N = 1, EV = FCFF/(1+W) + FCFF(1+g)/(W-g)/(1+W) = FCFF/(W-g), so
the value per share is 100,000 / (W - g) / 1,000 = 100 / (W - g):
| WACC  | g      | 100 / (W - g)   | exact      |
|-------|--------|-----------------|------------|
| 0.15  | 0.05   | 100 / 0.10      | 1,000      |
| 0.14  | 0.045  | 100 / 0.095     | 20,000/19  |
| 0.14  | 0.055  | 100 / 0.085     | 20,000/17  |
| 0.16  | 0.045  | 100 / 0.115     | 20,000/23  |
| 0.16  | 0.055  | 100 / 0.105     | 20,000/21  |
"""

from fractions import Fraction as F

import pytest

from intelligence.display import fmt
from intelligence.dcf import compute_dcf

CUR = {"revenue": 1_000_000, "cash": 50_000, "short_term_borrowings": 60_000,
       "long_term_borrowings": 140_000, "shares_outstanding": 10_000}
A = {"risk_free_rate": F("0.09"), "beta": F("1.5"), "equity_risk_premium": F("0.06"),
     "cost_of_debt": F("0.08"), "tax_rate": F("0.25"), "debt_weight": F("0.25"),
     "revenue_growth": F("0.10"), "ebit_margin": F("0.20"), "da_pct_revenue": F("0.05"),
     "capex_pct_revenue": F("0.06"), "nwc_pct_revenue": F("0.10"),
     "terminal_growth": F("0.05"), "forecast_years": F(2)}


@pytest.fixture
def v():
    r = compute_dcf(CUR, {}, A)
    assert r.computed
    return r


def test_capm_and_wacc(v):
    assert v.cost_of_equity == F("0.18")
    assert v.cost_of_debt == F("0.08")
    assert v.wacc == F("0.15")


def test_fcf_build_up(v):
    y1, y2 = v.years
    assert (y1.revenue, y1.ebit, y1.nopat, y1.da, y1.capex, y1.nwc_change, y1.fcff) == \
        (1_100_000, 220_000, 165_000, 55_000, 66_000, 10_000, 144_000)
    assert (y2.revenue, y2.nopat, y2.da, y2.capex, y2.nwc_change, y2.fcff) == \
        (1_210_000, 181_500, 60_500, 72_600, 11_000, 158_400)


def test_discounting(v):
    y1, y2 = v.years
    assert y1.pv == F(2_880_000, 23)
    assert y2.pv == F(63_360_000, 529)
    assert v.pv_fcff == F(129_600_000, 529)


def test_gordon_terminal_value(v):
    assert v.terminal_value == 1_663_200
    assert v.pv_terminal_value == F(665_280_000, 529)


def test_enterprise_equity_and_per_share(v):
    assert v.enterprise_value == F(794_880_000, 529)
    assert v.net_debt == 150_000
    assert v.equity_value == F(715_530_000, 529)
    assert v.per_share == F(3_111, 23)
    assert fmt(v.per_share, "per_share") == "PKR 135.26"


ONE_YEAR_CUR = {"revenue": 1_000_000, "cash": 50_000, "short_term_borrowings": 0,
                "long_term_borrowings": 50_000, "shares_outstanding": 1_000}
ONE_YEAR_A = {"risk_free_rate": F("0.09"), "beta": F(1), "equity_risk_premium": F("0.06"),
              "cost_of_debt": F("0.08"), "tax_rate": F("0.20"), "debt_weight": F(0),
              "revenue_growth": F(0), "ebit_margin": F("0.125"), "da_pct_revenue": F("0.05"),
              "capex_pct_revenue": F("0.05"), "nwc_pct_revenue": F("0.10"),
              "terminal_growth": F("0.05"), "forecast_years": F(1)}


def test_one_year_vector_is_fcff_over_w_minus_g():
    r = compute_dcf(ONE_YEAR_CUR, {}, ONE_YEAR_A)
    assert r.wacc == F("0.15") and r.years[0].fcff == 100_000
    assert r.per_share == 1_000


@pytest.mark.parametrize("wacc, g, expected", [
    (F("0.14"), F("0.045"), F(20_000, 19)),
    (F("0.14"), F("0.055"), F(20_000, 17)),
    (F("0.16"), F("0.045"), F(20_000, 23)),
    (F("0.16"), F("0.055"), F(20_000, 21)),
    (F("0.15"), F("0.05"), F(1_000)),
])
def test_sensitivity_grid_corners(wacc, g, expected):
    r = compute_dcf(ONE_YEAR_CUR, {}, ONE_YEAR_A)
    assert r.sensitivity[(wacc, g)] == expected


def test_sensitivity_grid_is_three_by_three():
    r = compute_dcf(ONE_YEAR_CUR, {}, ONE_YEAR_A)
    assert r.sensitivity_waccs == [F("0.14"), F("0.15"), F("0.16")]
    assert r.sensitivity_growths == [F("0.045"), F("0.05"), F("0.055")]


@pytest.mark.parametrize("g", [F("0.15"), F("0.16")])
def test_refuses_when_growth_is_not_below_wacc(g):
    r = compute_dcf(ONE_YEAR_CUR, {}, dict(ONE_YEAR_A, terminal_growth=g))
    assert not r.computed and r.per_share is None
    assert "must be below WACC" in r.refused


def test_grid_cells_where_growth_reaches_wacc_are_not_values():
    # Ke = 0 + 1 x 0.06, so WACC 6%; g 5%. The WACC 5% row has g >= WACC at g 5% and 5.5%.
    a = dict(ONE_YEAR_A, risk_free_rate=F(0), terminal_growth=F("0.05"))
    r = compute_dcf(ONE_YEAR_CUR, {}, a)
    assert r.wacc == F("0.06")
    assert r.sensitivity[(F("0.05"), F("0.055"))] is None
    assert r.sensitivity[(F("0.05"), F("0.05"))] is None
    assert r.sensitivity[(F("0.07"), F("0.045"))] == 100 / F("0.025")


def test_non_positive_shares_are_refused():
    r = compute_dcf(dict(ONE_YEAR_CUR, shares_outstanding=0), {}, ONE_YEAR_A)
    assert not r.computed and "Shares outstanding" in r.refused
