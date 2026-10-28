"""
intelligence/fields.py - The figures a user enters, per company type.

A company is a manufacturer, a non-manufacturer or a bank. The type decides which
fields the entry form shows and which models run. Changing the type never deletes
entered figures: fields that do not apply are hidden, and the analysis recomputes.

kind:
  money   - stored as whole rupees, entered in the analysis's reporting unit
  count   - a whole number (shares), entered as is
  percent - entered as a percentage, e.g. 15.4 for 15.4%
Signs: enter figures as the statement shows them. Costs, finance cost, tax and capital
expenditure are positive amounts; a loss, a tax credit or a cash outflow is negative.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPANY_TYPES: dict[str, str] = {
    "manufacturer": "Manufacturer",
    "non_manufacturer": "Non-manufacturer",
    "bank": "Bank",
}

NON_BANK = frozenset({"manufacturer", "non_manufacturer"})
BANK = frozenset({"bank"})
ALL_TYPES = NON_BANK | BANK

STATEMENTS: dict[str, str] = {
    "income": "Profit and loss",
    "balance": "Balance sheet",
    "cash_flow": "Cash flow",
    "other": "Other",
}

PERIODS = ("current", "prior")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    statement: str
    types: frozenset
    kind: str = "money"
    hint: str = ""
    page_ref: bool = False     # the form asks for the page the figure was taken from


FIELDS: tuple[Field, ...] = (
    # ── Non-bank: profit and loss ────────────────────────────────────────────
    Field("revenue", "Revenue (net sales)", "income", NON_BANK),
    Field("cost_of_sales", "Cost of sales", "income", NON_BANK, hint="positive"),
    Field("gross_profit", "Gross profit", "income", NON_BANK),
    Field("operating_profit", "Operating profit (EBIT)", "income", NON_BANK),
    Field("depreciation_amortisation", "Depreciation and amortisation", "income", NON_BANK,
          hint="positive"),
    Field("finance_cost", "Finance cost", "income", NON_BANK, hint="positive"),
    # ── Bank: profit and loss ────────────────────────────────────────────────
    Field("markup_earned", "Mark-up / interest earned", "income", BANK),
    Field("markup_expensed", "Mark-up / interest expensed", "income", BANK, hint="positive"),
    Field("net_markup_income", "Net mark-up / interest income", "income", BANK),
    Field("non_markup_income", "Non mark-up / interest income", "income", BANK),
    Field("operating_expenses", "Operating expenses", "income", BANK, hint="positive"),
    Field("provisions", "Provisions and write-offs (net charge)", "income", BANK,
          hint="positive; a net reversal is negative"),
    # ── Shared: profit and loss ──────────────────────────────────────────────
    Field("profit_before_tax", "Profit before tax", "income", ALL_TYPES),
    Field("tax_expense", "Taxation", "income", NON_BANK, hint="positive; a credit is negative"),
    Field("profit_after_tax", "Profit after tax", "income", ALL_TYPES),

    # ── Non-bank: balance sheet ──────────────────────────────────────────────
    Field("cash", "Cash and bank balances", "balance", NON_BANK),
    Field("trade_receivables", "Trade debts (receivables)", "balance", NON_BANK),
    Field("inventory", "Stock-in-trade (inventory)", "balance", NON_BANK),
    Field("current_assets", "Total current assets", "balance", NON_BANK),
    Field("trade_payables", "Trade and other payables", "balance", NON_BANK),
    Field("short_term_borrowings", "Short-term borrowings", "balance", NON_BANK,
          hint="including the current portion of long-term debt"),
    Field("current_liabilities", "Total current liabilities", "balance", NON_BANK),
    Field("long_term_borrowings", "Long-term borrowings", "balance", NON_BANK,
          hint="non-current portion"),
    Field("total_liabilities", "Total liabilities", "balance", NON_BANK),
    Field("retained_earnings", "Retained earnings (unappropriated profit)", "balance", NON_BANK),
    # ── Bank: balance sheet ──────────────────────────────────────────────────
    Field("gross_advances", "Advances, gross", "balance", BANK),
    Field("advance_provisions", "Provisions held against advances", "balance", BANK,
          hint="positive"),
    Field("net_advances", "Advances, net of provisions", "balance", BANK),
    Field("npls", "Non-performing loans (NPLs)", "balance", BANK),
    Field("investments", "Investments", "balance", BANK),
    Field("earning_assets", "Earning assets, if disclosed", "balance", BANK),
    Field("deposits", "Deposits and other accounts", "balance", BANK),
    Field("casa_deposits", "Current and savings deposits (CASA), if disclosed", "balance", BANK),
    # ── Shared: balance sheet ────────────────────────────────────────────────
    Field("total_assets", "Total assets", "balance", ALL_TYPES),
    Field("total_equity", "Total equity", "balance", ALL_TYPES),

    # ── Non-bank: cash flow ──────────────────────────────────────────────────
    Field("cash_from_operations", "Net cash from operating activities", "cash_flow", NON_BANK),
    Field("capital_expenditure", "Capital expenditure", "cash_flow", NON_BANK,
          hint="positive amount spent"),
    Field("cash_from_investing", "Net cash from investing activities", "cash_flow", NON_BANK,
          hint="an outflow is negative"),
    Field("cash_from_financing", "Net cash from financing activities", "cash_flow", NON_BANK,
          hint="an outflow is negative"),

    # ── Other ────────────────────────────────────────────────────────────────
    Field("shares_outstanding", "Shares outstanding", "other", ALL_TYPES, kind="count",
          hint="number of shares"),
    Field("car_reported", "Capital adequacy ratio, as reported", "other", BANK,
          kind="percent", hint="%", page_ref=True),
)

FIELD_BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}


def fields_for(company_type: str) -> list[Field]:
    """The fields the entry form shows for a company type, in statement order."""
    if company_type not in COMPANY_TYPES:
        raise ValueError(f"unknown company type {company_type!r}")
    return [f for f in FIELDS if company_type in f.types]


def grouped_fields(company_type: str) -> list[tuple[str, list[Field]]]:
    """[(statement label, [fields])] for the entry form."""
    fs = fields_for(company_type)
    return [(label, [f for f in fs if f.statement == key])
            for key, label in STATEMENTS.items()
            if any(f.statement == key for f in fs)]
