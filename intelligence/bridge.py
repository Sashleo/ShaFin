"""
intelligence/bridge.py - Profit bridge: what moved profit after tax from last year.

The components are defined so that they sum exactly to the change in profit after
tax, in whole rupees, whatever was entered:

Non-banks, using the identity
  PAT = Revenue - Cost of sales - Operating costs - Finance cost - Tax + Other
  Operating costs = (Revenue - Cost of sales) - Operating profit
  Other           = PAT - (Operating profit - Finance cost - Tax)
Banks, using the identity
  PAT = Net mark-up income + Non mark-up income - Operating expenses - Provisions
        + Other - Tax
  Tax   = Profit before tax - PAT
  Other = Profit before tax - (Net mark-up income + Non mark-up income
                               - Operating expenses - Provisions)
Each component is the year-on-year change of its term, with the sign it has in PAT.
"Other" collects whatever the entered statement has between those lines (other
income, associates, rounding) and is zero when the profit chain is complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from intelligence.ratios import label_of

_NON_BANK_NEED = ("revenue", "cost_of_sales", "operating_profit", "finance_cost", "tax_expense",
                  "profit_after_tax")
_BANK_NEED = ("net_markup_income", "non_markup_income", "operating_expenses", "provisions",
              "profit_before_tax", "profit_after_tax")


@dataclass
class Bridge:
    components: list = field(default_factory=list)   # [(label, rupees)]
    start: Optional[int] = None                       # prior PAT
    end: Optional[int] = None                         # current PAT
    missing: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(v for _, v in self.components)


def _terms_non_bank(p: dict) -> list:
    operating_costs = (p["revenue"] - p["cost_of_sales"]) - p["operating_profit"]
    other = p["profit_after_tax"] - (p["operating_profit"] - p["finance_cost"] - p["tax_expense"])
    return [("Revenue", p["revenue"]), ("Cost of sales", -p["cost_of_sales"]),
            ("Operating costs", -operating_costs), ("Finance cost", -p["finance_cost"]),
            ("Taxation", -p["tax_expense"]), ("Other items", other)]


def _terms_bank(p: dict) -> list:
    core = (p["net_markup_income"] + p["non_markup_income"] - p["operating_expenses"]
            - p["provisions"])
    tax = p["profit_before_tax"] - p["profit_after_tax"]
    return [("Net mark-up income", p["net_markup_income"]),
            ("Non mark-up income", p["non_markup_income"]),
            ("Operating expenses", -p["operating_expenses"]), ("Provisions", -p["provisions"]),
            ("Other items", p["profit_before_tax"] - core), ("Taxation", -tax)]


def compute_bridge(company_type: str, cur: dict, prior: dict) -> Bridge:
    bank = company_type == "bank"
    need = _BANK_NEED if bank else _NON_BANK_NEED
    b = Bridge()
    b.missing = [f"{label_of(k)} ({period})" for period, facts in (("current", cur), ("prior", prior))
                 for k in need if facts.get(k) is None]
    if b.missing:
        return b
    terms = _terms_bank if bank else _terms_non_bank
    b.components = [(label, now - before)
                    for (label, now), (_, before) in zip(terms(cur), terms(prior))]
    b.start, b.end = prior["profit_after_tax"], cur["profit_after_tax"]
    return b
