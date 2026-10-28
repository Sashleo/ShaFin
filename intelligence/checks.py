"""
intelligence/checks.py - Do the entered statements add up?

Each check compares two sides of an accounting identity in whole rupees. A check
passes when the difference is at most one unit of the analysis's reporting unit
(published statements are rounded to that unit). A check whose figures are not all
entered is skipped and says which are missing. Checks are reported, never enforced:
the analysis still runs on what was entered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from intelligence.ratios import label_of


@dataclass
class Check:
    label: str
    left: Optional[int] = None
    right: Optional[int] = None
    passed: Optional[bool] = None     # None: not run
    missing: tuple = ()

    @property
    def difference(self) -> Optional[int]:
        return None if self.left is None else self.left - self.right


def _check(label: str, facts: dict, left: tuple, right: tuple, tolerance: int) -> Check:
    """left and right are ((sign, key), ...) sums over the entered facts."""
    keys = [k for _, k in left + right]
    missing = tuple(label_of(k) for k in keys if facts.get(k) is None)
    if missing:
        return Check(label, missing=missing)
    lv = sum(s * facts[k] for s, k in left)
    rv = sum(s * facts[k] for s, k in right)
    return Check(label, lv, rv, abs(lv - rv) <= tolerance)


def _cash_flow_check(cur: dict, prior: dict, tolerance: int) -> Check:
    label = "Cash flow: operating + investing + financing = change in cash"
    need = {"cash_from_operations": cur, "cash_from_investing": cur, "cash_from_financing": cur,
            "cash": cur}
    missing = [label_of(k) for k, src in need.items() if src.get(k) is None]
    if prior.get("cash") is None:
        missing.append("Cash and bank balances (prior)")
    if missing:
        return Check(label, missing=tuple(missing))
    flows = cur["cash_from_operations"] + cur["cash_from_investing"] + cur["cash_from_financing"]
    change = cur["cash"] - prior["cash"]
    return Check(label, flows, change, abs(flows - change) <= tolerance)


def run_checks(company_type: str, cur: dict, prior: dict, tolerance: int) -> list[Check]:
    P, M = 1, -1
    if company_type == "bank":
        return [
            _check("Net mark-up income = earned - expensed", cur,
                   ((P, "net_markup_income"),), ((P, "markup_earned"), (M, "markup_expensed")),
                   tolerance),
            _check("Net advances = gross advances - provisions held", cur,
                   ((P, "net_advances"),), ((P, "gross_advances"), (M, "advance_provisions")),
                   tolerance),
            _check("Profit before tax = net mark-up income + non mark-up income "
                   "- operating expenses - provisions", cur,
                   ((P, "profit_before_tax"),),
                   ((P, "net_markup_income"), (P, "non_markup_income"),
                    (M, "operating_expenses"), (M, "provisions")), tolerance),
        ]
    return [
        _check("Balance sheet: total assets = total liabilities + total equity", cur,
               ((P, "total_assets"),), ((P, "total_liabilities"), (P, "total_equity")), tolerance),
        _check("Gross profit = revenue - cost of sales", cur,
               ((P, "gross_profit"),), ((P, "revenue"), (M, "cost_of_sales")), tolerance),
        _check("Profit before tax = operating profit - finance cost", cur,
               ((P, "profit_before_tax"),), ((P, "operating_profit"), (M, "finance_cost")),
               tolerance),
        _check("Profit after tax = profit before tax - taxation", cur,
               ((P, "profit_after_tax"),), ((P, "profit_before_tax"), (M, "tax_expense")),
               tolerance),
        _cash_flow_check(cur, prior, tolerance),
    ]
