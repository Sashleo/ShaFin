"""
intelligence/dcf.py - Free cash flow to the firm, discounted at WACC, for non-banks.

Every rate and driver is an assumption entered for the analysis (see
intelligence/assumptions.py). Nothing is defaulted: when an input is missing the
DCF does not run and names what is required. Exact Fraction arithmetic throughout.

  Revenue_t = Revenue_(t-1) x (1 + revenue growth), Revenue_0 = current revenue
  FCFF_t    = Revenue_t x EBIT margin x (1 - tax rate)
              + Revenue_t x D&A % - Revenue_t x capex %
              - (Revenue_t - Revenue_(t-1)) x working-capital %
  Ke   = risk-free rate + beta x equity risk premium              (CAPM)
  Kd   = cost of debt, if entered; otherwise
         finance cost / average borrowings (current and prior year)
  WACC = (1 - debt weight) x Ke + debt weight x Kd x (1 - tax rate)
  PV   = sum of FCFF_t / (1 + WACC)^t, t = 1..N (end-of-year discounting)
  TV   = FCFF_N x (1 + g) / (WACC - g)                            (Gordon growth)
  EV   = PV + TV / (1 + WACC)^N
  Equity = EV - (borrowings - cash); per share = Equity / shares outstanding
Refuses when g >= WACC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from intelligence.assumptions import ASSUMPTION_BY_KEY
from intelligence.ratios import label_of

# Sensitivity grid: WACC and terminal growth moved by these amounts (percentage points).
WACC_STEPS = (Fraction(-1, 100), Fraction(0), Fraction(1, 100))
GROWTH_STEPS = (Fraction(-1, 200), Fraction(0), Fraction(1, 200))

_REQUIRED_ASSUMPTIONS = ("risk_free_rate", "equity_risk_premium", "beta", "tax_rate",
                         "terminal_growth", "forecast_years", "debt_weight", "revenue_growth",
                         "ebit_margin", "da_pct_revenue", "capex_pct_revenue", "nwc_pct_revenue")
_REQUIRED_FACTS = ("revenue", "cash", "short_term_borrowings", "long_term_borrowings",
                   "shares_outstanding")


@dataclass
class YearRow:
    year: int
    revenue: Fraction
    ebit: Fraction
    nopat: Fraction
    da: Fraction
    capex: Fraction
    nwc_change: Fraction
    fcff: Fraction
    discount_factor: Fraction
    pv: Fraction


@dataclass
class DCFResult:
    computed: bool = False
    missing: list = field(default_factory=list)
    refused: str = ""
    cost_of_equity: Optional[Fraction] = None
    cost_of_debt: Optional[Fraction] = None
    cost_of_debt_basis: str = ""
    wacc: Optional[Fraction] = None
    years: list = field(default_factory=list)
    pv_fcff: Optional[Fraction] = None
    terminal_value: Optional[Fraction] = None
    pv_terminal_value: Optional[Fraction] = None
    enterprise_value: Optional[Fraction] = None
    net_debt: Optional[int] = None
    equity_value: Optional[Fraction] = None
    per_share: Optional[Fraction] = None
    terminal_share: Optional[Fraction] = None        # PV of TV / EV
    sensitivity: dict = field(default_factory=dict)  # {(wacc, g): per share or None}

    @property
    def sensitivity_waccs(self) -> list:
        return sorted({w for w, _ in self.sensitivity})

    @property
    def sensitivity_growths(self) -> list:
        return sorted({g for _, g in self.sensitivity})


def _value_per_share(fcffs: list, wacc: Fraction, g: Fraction, net_debt, shares) -> Optional[Fraction]:
    if g >= wacc:
        return None
    n = len(fcffs)
    pv = sum(f / (1 + wacc) ** t for t, f in enumerate(fcffs, 1))
    ev = pv + fcffs[-1] * (1 + g) / (wacc - g) / (1 + wacc) ** n
    return (ev - net_debt) / shares


def compute_dcf(cur: dict, prior: dict, a: dict) -> DCFResult:
    """cur/prior: entered facts (whole rupees). a: assumption values (Fractions)."""
    r = DCFResult()
    r.missing = [f"{ASSUMPTION_BY_KEY[k].label} (assumption)"
                 for k in _REQUIRED_ASSUMPTIONS if a.get(k) is None]
    r.missing += [label_of(k) for k in _REQUIRED_FACTS if cur.get(k) is None]

    kd = a.get("cost_of_debt")
    if kd is not None:
        r.cost_of_debt_basis = "Entered as an assumption."
    else:
        need = {"Finance cost": cur.get("finance_cost"),
                "Short-term borrowings": cur.get("short_term_borrowings"),
                "Long-term borrowings": cur.get("long_term_borrowings"),
                "Prior-year short-term borrowings": prior.get("short_term_borrowings"),
                "Prior-year long-term borrowings": prior.get("long_term_borrowings")}
        absent = [k for k, v in need.items() if v is None]
        if absent:
            r.missing.append("Cost of debt (assumption), or to compute it: " + ", ".join(absent))
        else:
            avg = Fraction(cur["short_term_borrowings"] + cur["long_term_borrowings"]
                           + prior["short_term_borrowings"] + prior["long_term_borrowings"], 2)
            if avg == 0:
                r.missing.append("Cost of debt (assumption): average borrowings are zero")
            else:
                kd = Fraction(cur["finance_cost"]) / avg
                r.cost_of_debt_basis = (
                    "Computed: finance cost / average borrowings = "
                    f"{cur['finance_cost']:,} / {float(avg):,.0f}")
    if r.missing:
        return r
    if cur["shares_outstanding"] <= 0:
        r.refused = "Shares outstanding must be positive."
        return r

    t, g = a["tax_rate"], a["terminal_growth"]
    r.cost_of_equity = a["risk_free_rate"] + a["beta"] * a["equity_risk_premium"]
    r.cost_of_debt = kd
    wd = a["debt_weight"]
    r.wacc = (1 - wd) * r.cost_of_equity + wd * kd * (1 - t)
    if g >= r.wacc:
        r.refused = (f"Terminal growth ({float(g):.2%}) must be below WACC ({float(r.wacc):.2%}); "
                     "the Gordon terminal value is not defined otherwise.")
        return r

    prev = Fraction(cur["revenue"])
    for year in range(1, int(a["forecast_years"]) + 1):
        rev = prev * (1 + a["revenue_growth"])
        ebit = rev * a["ebit_margin"]
        nopat = ebit * (1 - t)
        da = rev * a["da_pct_revenue"]
        capex = rev * a["capex_pct_revenue"]
        dnwc = (rev - prev) * a["nwc_pct_revenue"]
        fcff = nopat + da - capex - dnwc
        df = 1 / (1 + r.wacc) ** year
        r.years.append(YearRow(year, rev, ebit, nopat, da, capex, dnwc, fcff, df, fcff * df))
        prev = rev

    n = len(r.years)
    r.pv_fcff = sum(y.pv for y in r.years)
    r.terminal_value = r.years[-1].fcff * (1 + g) / (r.wacc - g)
    r.pv_terminal_value = r.terminal_value / (1 + r.wacc) ** n
    r.enterprise_value = r.pv_fcff + r.pv_terminal_value
    r.net_debt = cur["short_term_borrowings"] + cur["long_term_borrowings"] - cur["cash"]
    r.equity_value = r.enterprise_value - r.net_debt
    r.per_share = r.equity_value / cur["shares_outstanding"]
    r.terminal_share = r.pv_terminal_value / r.enterprise_value if r.enterprise_value else None

    fcffs = [y.fcff for y in r.years]
    for dw in WACC_STEPS:
        for dg in GROWTH_STEPS:
            r.sensitivity[(r.wacc + dw, g + dg)] = _value_per_share(
                fcffs, r.wacc + dw, g + dg, r.net_debt, cur["shares_outstanding"])
    r.computed = True
    return r
