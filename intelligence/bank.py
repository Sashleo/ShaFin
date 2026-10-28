"""
intelligence/bank.py - Bank ratios and the bank valuation view.

Banks get no Altman score (Altman's samples excluded financial companies) and no
DCF (deposits are a bank's raw material, not financing, so free cash flow to the
firm does not describe a bank). They get price-to-book beside return on equity,
and price-to-earnings, from a share price the user enters.
"""

from __future__ import annotations

from fractions import Fraction

from intelligence.ratios import Metric, metric


def _average(a, b):
    return Fraction(a + b, 2)


def compute_nim(cur: dict, prior: dict) -> Metric:
    """Net interest margin over average earning assets, else average total assets."""
    m = Metric("nim", "Net interest margin", "pct", "Net mark-up income / Average earning assets")
    if cur.get("net_markup_income") is None:
        m.missing = ["Net mark-up / interest income"]
        return m
    if cur.get("earning_assets") is not None and prior.get("earning_assets") is not None:
        base, basis = _average(cur["earning_assets"], prior["earning_assets"]), \
            "Basis: average earning assets (current and prior)."
    elif cur.get("total_assets") is not None and prior.get("total_assets") is not None:
        base, basis = _average(cur["total_assets"], prior["total_assets"]), \
            "Basis: average total assets, because earning assets are not entered for both years."
        m.formula = "Net mark-up income / Average total assets"
    else:
        m.missing = ["Earning assets or total assets, for the current and prior year"]
        return m
    if base == 0:
        m.note = "Not defined: the average base is zero."
        return m
    m.value = Fraction(cur["net_markup_income"]) / base
    m.note = basis
    return m


def compute_bank_ratios(cur: dict, prior: dict) -> list[Metric]:
    g = cur.get
    car = Metric("car_reported", "Capital adequacy ratio (as reported)", "pct",
                 "As reported by the bank")
    if g("car_reported") is None:
        car.missing = ["Capital adequacy ratio, as reported"]
    else:
        car.value = g("car_reported")
        car.note = "Entered as reported" + (f", page {g('car_reported_page')}"
                                            if g("car_reported_page") else "") + "."
    return [
        compute_nim(cur, prior),
        metric("cost_to_income", "Cost to income", "pct",
               "Operating expenses / (Net mark-up income + Non mark-up income)",
               {"operating_expenses": g("operating_expenses"),
                "net_markup_income": g("net_markup_income"),
                "non_markup_income": g("non_markup_income")},
               lambda operating_expenses, net_markup_income, non_markup_income:
                   Fraction(operating_expenses, net_markup_income + non_markup_income)),
        metric("roe", "Return on equity", "pct", "Profit after tax / Total equity",
               {"profit_after_tax": g("profit_after_tax"), "total_equity": g("total_equity")},
               lambda profit_after_tax, total_equity: Fraction(profit_after_tax, total_equity)),
        metric("roa", "Return on assets", "pct", "Profit after tax / Total assets",
               {"profit_after_tax": g("profit_after_tax"), "total_assets": g("total_assets")},
               lambda profit_after_tax, total_assets: Fraction(profit_after_tax, total_assets)),
        metric("advances_to_deposits", "Advances to deposits", "pct",
               "Gross advances / Deposits",
               {"gross_advances": g("gross_advances"), "deposits": g("deposits")},
               lambda gross_advances, deposits: Fraction(gross_advances, deposits)),
        metric("casa_share", "CASA share of deposits", "pct", "CASA deposits / Deposits",
               {"casa_deposits": g("casa_deposits"), "deposits": g("deposits")},
               lambda casa_deposits, deposits: Fraction(casa_deposits, deposits)),
        metric("npl_ratio", "NPL ratio", "pct", "NPLs / Gross advances",
               {"npls": g("npls"), "gross_advances": g("gross_advances")},
               lambda npls, gross_advances: Fraction(npls, gross_advances)),
        metric("coverage", "Provision coverage", "pct", "Provisions held against advances / NPLs",
               {"advance_provisions": g("advance_provisions"), "npls": g("npls")},
               lambda advance_provisions, npls: Fraction(advance_provisions, npls),
               "Not defined: NPLs are zero."),
        metric("equity_to_assets", "Equity to assets", "pct", "Total equity / Total assets",
               {"total_equity": g("total_equity"), "total_assets": g("total_assets")},
               lambda total_equity, total_assets: Fraction(total_equity, total_assets)),
        car,
        metric("eps", "Earnings per share", "per_share", "Profit after tax / Shares outstanding",
               {"profit_after_tax": g("profit_after_tax"),
                "shares_outstanding": g("shares_outstanding")},
               lambda profit_after_tax, shares_outstanding:
                   Fraction(profit_after_tax, shares_outstanding)),
    ]


def compute_bank_valuation(cur: dict, share_price) -> list[Metric]:
    """Price-to-book (shown beside ROE) and price-to-earnings, from an entered share price."""
    g = cur.get
    price = {"share price": share_price}

    def pe(**kw):
        eps = Fraction(kw["profit_after_tax"], kw["shares_outstanding"])
        if eps <= 0:
            raise ZeroDivisionError
        return kw["share price"] / eps

    return [
        metric("book_value_per_share", "Book value per share", "per_share",
               "Total equity / Shares outstanding",
               {"total_equity": g("total_equity"), "shares_outstanding": g("shares_outstanding")},
               lambda total_equity, shares_outstanding: Fraction(total_equity, shares_outstanding)),
        metric("pb", "Price to book", "x", "Share price / (Total equity / Shares outstanding)",
               {**price, "total_equity": g("total_equity"),
                "shares_outstanding": g("shares_outstanding")},
               lambda **kw: kw["share price"] / Fraction(kw["total_equity"], kw["shares_outstanding"]),
               "Not defined: book value is zero."),
        metric("pe", "Price to earnings", "x",
               "Share price / (Profit after tax / Shares outstanding)",
               {**price, "profit_after_tax": g("profit_after_tax"),
                "shares_outstanding": g("shares_outstanding")},
               pe, "Not defined: earnings per share is zero or negative."),
    ]
