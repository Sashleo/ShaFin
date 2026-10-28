"""
intelligence/assumptions.py - The per-analysis assumptions panel.

ShaFin has no default and no fallback for any rate. Every assumption is entered for
one analysis, with a required "source and date", and printed in that analysis's
reports. A model that needs an assumption that is not entered does not run; it says
"Required: <assumption>".
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from intelligence.fields import ALL_TYPES, NON_BANK
from intelligence.units import UnitError, parse_number


@dataclass(frozen=True)
class Assumption:
    key: str
    label: str
    unit: str          # "pct" (entered as a percentage), "x", "years" or "pkr"
    types: frozenset
    used_by: str
    optional: bool = False
    hint: str = ""


ASSUMPTIONS: tuple[Assumption, ...] = (
    Assumption("risk_free_rate", "Risk-free rate", "pct", NON_BANK, "DCF: cost of equity"),
    Assumption("equity_risk_premium", "Equity risk premium", "pct", NON_BANK,
               "DCF: cost of equity"),
    Assumption("beta", "Beta", "x", NON_BANK, "DCF: cost of equity"),
    Assumption("tax_rate", "Corporate tax rate", "pct", NON_BANK, "DCF: NOPAT and WACC"),
    Assumption("terminal_growth", "Terminal growth", "pct", NON_BANK, "DCF: terminal value"),
    Assumption("forecast_years", "Forecast years", "years", NON_BANK, "DCF: projection",
               hint="whole number, 1 to 15"),
    Assumption("cost_of_debt", "Cost of debt", "pct", NON_BANK, "DCF: WACC", optional=True,
               hint="leave empty to use finance cost / average borrowings"),
    Assumption("debt_weight", "Debt weight in WACC", "pct", NON_BANK, "DCF: WACC",
               hint="0 to 100"),
    Assumption("revenue_growth", "Revenue growth per year", "pct", NON_BANK, "DCF: projection"),
    Assumption("ebit_margin", "EBIT margin", "pct", NON_BANK, "DCF: projection"),
    Assumption("da_pct_revenue", "Depreciation and amortisation, % of revenue", "pct",
               NON_BANK, "DCF: projection"),
    Assumption("capex_pct_revenue", "Capital expenditure, % of revenue", "pct", NON_BANK,
               "DCF: projection"),
    Assumption("nwc_pct_revenue", "Working-capital investment, % of the revenue increase",
               "pct", NON_BANK, "DCF: projection"),
    Assumption("share_price", "Share price", "pkr", ALL_TYPES,
               "Altman Z (manufacturers), P/B and P/E, DCF comparison", optional=True),
)

ASSUMPTION_BY_KEY: dict[str, Assumption] = {a.key: a for a in ASSUMPTIONS}


def assumptions_for(company_type: str) -> list[Assumption]:
    return [a for a in ASSUMPTIONS if company_type in a.types]


def parse_assumption(key: str, text: str) -> Fraction:
    """The model value of an entered assumption: percentages become fractions (12 -> 0.12)."""
    a = ASSUMPTION_BY_KEY[key]
    value = parse_number(text)
    if a.unit == "pct":
        if key == "debt_weight" and not 0 <= value <= 100:
            raise UnitError("debt weight must be between 0 and 100")
        return value / 100
    if a.unit == "years":
        if value.denominator != 1 or not 1 <= value <= 15:
            raise UnitError("forecast years must be a whole number from 1 to 15")
    if a.unit == "pkr" and value <= 0:
        raise UnitError("share price must be positive")
    return value
