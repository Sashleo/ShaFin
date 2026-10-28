"""
intelligence/ratios.py - Ratios for manufacturers and non-manufacturers, and DuPont.

Pure functions over entered figures (whole rupees) with exact Fraction arithmetic;
nothing is rounded until it is displayed. Balance-sheet figures are closing balances
of the current period. Every formula is defined once in docs/CALCULATIONS.md.

A metric whose inputs are not all entered is not computed; it lists what is
required. A division by zero is reported as "not defined", never as zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable, Optional

from intelligence.fields import FIELD_BY_KEY

DAYS_IN_YEAR = 365


@dataclass
class Metric:
    key: str
    label: str
    unit: str            # "pct", "x", "days", "pkr", "per_share"
    formula: str
    value: Optional[Fraction] = None
    missing: list = field(default_factory=list)
    note: str = ""

    @property
    def computed(self) -> bool:
        return self.value is not None


def label_of(key: str) -> str:
    """Display label for an input: the field label, or the key for derived inputs."""
    return FIELD_BY_KEY[key].label if key in FIELD_BY_KEY else key


def metric(key: str, label: str, unit: str, formula: str, inputs: dict,
           fn: Callable[..., Fraction], undefined_note: str = "") -> Metric:
    """Evaluate fn(**inputs) when every input is entered; otherwise list what is required."""
    m = Metric(key, label, unit, formula)
    missing = [label_of(k) for k, v in inputs.items() if v is None]
    if missing:
        m.missing = missing
        return m
    try:
        m.value = Fraction(fn(**inputs))
    except ZeroDivisionError:
        m.note = undefined_note or "Not defined: a denominator is zero."
    return m


def _growth(cur, prior) -> Fraction:
    if prior <= 0:
        raise ZeroDivisionError
    return Fraction(cur - prior, prior)


def compute_ratios(cur: dict, prior: dict) -> list[Metric]:
    """Non-bank ratios. cur and prior map field keys to whole rupees (or counts)."""
    g = cur.get
    return [
        metric("gross_margin", "Gross margin", "pct", "Gross profit / Revenue",
               {"gross_profit": g("gross_profit"), "revenue": g("revenue")},
               lambda gross_profit, revenue: Fraction(gross_profit, revenue)),
        metric("operating_margin", "Operating margin", "pct", "Operating profit / Revenue",
               {"operating_profit": g("operating_profit"), "revenue": g("revenue")},
               lambda operating_profit, revenue: Fraction(operating_profit, revenue)),
        metric("net_margin", "Net margin", "pct", "Profit after tax / Revenue",
               {"profit_after_tax": g("profit_after_tax"), "revenue": g("revenue")},
               lambda profit_after_tax, revenue: Fraction(profit_after_tax, revenue)),
        metric("roe", "Return on equity", "pct", "Profit after tax / Total equity",
               {"profit_after_tax": g("profit_after_tax"), "total_equity": g("total_equity")},
               lambda profit_after_tax, total_equity: Fraction(profit_after_tax, total_equity)),
        metric("roa", "Return on assets", "pct", "Profit after tax / Total assets",
               {"profit_after_tax": g("profit_after_tax"), "total_assets": g("total_assets")},
               lambda profit_after_tax, total_assets: Fraction(profit_after_tax, total_assets)),
        metric("current_ratio", "Current ratio", "x",
               "Total current assets / Total current liabilities",
               {"current_assets": g("current_assets"), "current_liabilities": g("current_liabilities")},
               lambda current_assets, current_liabilities:
                   Fraction(current_assets, current_liabilities)),
        metric("quick_ratio", "Quick ratio", "x",
               "(Total current assets - Inventory) / Total current liabilities",
               {"current_assets": g("current_assets"), "inventory": g("inventory"),
                "current_liabilities": g("current_liabilities")},
               lambda current_assets, inventory, current_liabilities:
                   Fraction(current_assets - inventory, current_liabilities)),
        metric("debt_to_equity", "Debt to equity", "x",
               "(Short-term + Long-term borrowings) / Total equity",
               {"short_term_borrowings": g("short_term_borrowings"),
                "long_term_borrowings": g("long_term_borrowings"),
                "total_equity": g("total_equity")},
               lambda short_term_borrowings, long_term_borrowings, total_equity:
                   Fraction(short_term_borrowings + long_term_borrowings, total_equity)),
        metric("liabilities_to_assets", "Liabilities to assets", "pct",
               "Total liabilities / Total assets",
               {"total_liabilities": g("total_liabilities"), "total_assets": g("total_assets")},
               lambda total_liabilities, total_assets: Fraction(total_liabilities, total_assets)),
        metric("equity_multiplier", "Equity multiplier", "x", "Total assets / Total equity",
               {"total_assets": g("total_assets"), "total_equity": g("total_equity")},
               lambda total_assets, total_equity: Fraction(total_assets, total_equity)),
        metric("interest_coverage", "Interest coverage", "x", "Operating profit / Finance cost",
               {"operating_profit": g("operating_profit"), "finance_cost": g("finance_cost")},
               lambda operating_profit, finance_cost: Fraction(operating_profit, finance_cost),
               "Not defined: finance cost is zero."),
        metric("asset_turnover", "Asset turnover", "x", "Revenue / Total assets",
               {"revenue": g("revenue"), "total_assets": g("total_assets")},
               lambda revenue, total_assets: Fraction(revenue, total_assets)),
        metric("days_receivable", "Days receivable", "days",
               "Trade debts / Revenue x 365",
               {"trade_receivables": g("trade_receivables"), "revenue": g("revenue")},
               lambda trade_receivables, revenue:
                   Fraction(trade_receivables, revenue) * DAYS_IN_YEAR),
        metric("days_inventory", "Days inventory", "days",
               "Stock-in-trade / Cost of sales x 365",
               {"inventory": g("inventory"), "cost_of_sales": g("cost_of_sales")},
               lambda inventory, cost_of_sales: Fraction(inventory, cost_of_sales) * DAYS_IN_YEAR),
        metric("days_payable", "Days payable", "days",
               "Trade and other payables / Cost of sales x 365",
               {"trade_payables": g("trade_payables"), "cost_of_sales": g("cost_of_sales")},
               lambda trade_payables, cost_of_sales:
                   Fraction(trade_payables, cost_of_sales) * DAYS_IN_YEAR),
        metric("free_cash_flow", "Free cash flow", "pkr",
               "Net cash from operating activities - Capital expenditure",
               {"cash_from_operations": g("cash_from_operations"),
                "capital_expenditure": g("capital_expenditure")},
               lambda cash_from_operations, capital_expenditure:
                   cash_from_operations - capital_expenditure),
        metric("eps", "Earnings per share", "per_share", "Profit after tax / Shares outstanding",
               {"profit_after_tax": g("profit_after_tax"),
                "shares_outstanding": g("shares_outstanding")},
               lambda profit_after_tax, shares_outstanding:
                   Fraction(profit_after_tax, shares_outstanding)),
        metric("revenue_growth", "Revenue growth", "pct",
               "(Revenue - prior Revenue) / prior Revenue",
               {"revenue": g("revenue"), "prior revenue": prior.get("revenue")},
               lambda **kw: _growth(kw["revenue"], kw["prior revenue"]),
               "Not defined: prior revenue is zero or negative."),
        metric("pat_growth", "Profit after tax growth", "pct",
               "(Profit after tax - prior) / prior",
               {"profit_after_tax": g("profit_after_tax"),
                "prior profit after tax": prior.get("profit_after_tax")},
               lambda **kw: _growth(kw["profit_after_tax"], kw["prior profit after tax"]),
               "Not defined: prior profit is zero or a loss."),
    ]


@dataclass
class DuPont:
    net_margin: Optional[Fraction] = None
    asset_turnover: Optional[Fraction] = None
    equity_multiplier: Optional[Fraction] = None
    roe: Optional[Fraction] = None
    missing: list = field(default_factory=list)


def compute_dupont(cur: dict) -> DuPont:
    """ROE = net margin x asset turnover x equity multiplier, on the same closing balances."""
    need = ("profit_after_tax", "revenue", "total_assets", "total_equity")
    d = DuPont(missing=[label_of(k) for k in need if cur.get(k) is None])
    if d.missing or 0 in (cur["revenue"], cur["total_assets"], cur["total_equity"]):
        return d
    d.net_margin = Fraction(cur["profit_after_tax"], cur["revenue"])
    d.asset_turnover = Fraction(cur["revenue"], cur["total_assets"])
    d.equity_multiplier = Fraction(cur["total_assets"], cur["total_equity"])
    d.roe = d.net_margin * d.asset_turnover * d.equity_multiplier
    return d
