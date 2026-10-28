"""
intelligence/altman.py - Altman Z-scores, chosen by company type.

Manufacturers: the original Z (Altman 1968).
    Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5
    X4 = market value of equity / total liabilities; X5 = revenue / total assets
    Safe above 2.99, distress below 1.81, grey from 1.81 to 2.99 inclusive.
Non-manufacturers: Z'' (Altman 2000), which drops X5 and uses book equity.
    Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4
    X4 = book equity / total liabilities
    Safe above 2.60, distress below 1.10, grey from 1.10 to 2.60 inclusive.
    This is Z'' without the +3.25 constant: the constant belongs to the separate
    emerging-market score, whose cut-offs are different.
Both: X1 = (current assets - current liabilities) / total assets,
      X2 = retained earnings / total assets, X3 = EBIT / total assets.
Banks: not applicable.

Every input is required; there is no partial score. Citations are in
docs/CALCULATIONS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from intelligence.ratios import label_of

F = Fraction


@dataclass(frozen=True)
class AltmanModel:
    name: str
    coefficients: tuple          # X1..Xn
    safe_above: Fraction
    distress_below: Fraction
    citation: str


Z_ORIGINAL = AltmanModel(
    "Altman Z (manufacturers)",
    (F("1.2"), F("1.4"), F("3.3"), F("0.6"), F("1.0")),
    F("2.99"), F("1.81"),
    "Altman, E. I. (1968). Financial ratios, discriminant analysis and the prediction of "
    "corporate bankruptcy. The Journal of Finance, 23(4), 589-609.",
)

Z_DOUBLE_PRIME = AltmanModel(
    "Altman Z'' (non-manufacturers)",
    (F("6.56"), F("3.26"), F("6.72"), F("1.05")),
    F("2.60"), F("1.10"),
    "Altman, E. I. (2000). Predicting financial distress of companies: revisiting the "
    "Z-score and ZETA models. Stern School of Business, New York University; also "
    "Altman & Hotchkiss (2006), Corporate Financial Distress and Bankruptcy, 3rd ed., Wiley.",
)


@dataclass
class AltmanResult:
    applicable: bool
    model: Optional[AltmanModel] = None
    z: Optional[Fraction] = None
    zone: str = ""                     # "safe", "grey", "distress"
    components: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    note: str = ""


def zone_for(z: Fraction, model: AltmanModel) -> str:
    if z > model.safe_above:
        return "safe"
    if z < model.distress_below:
        return "distress"
    return "grey"


def compute_altman(company_type: str, cur: dict, share_price=None) -> AltmanResult:
    if company_type == "bank":
        return AltmanResult(applicable=False, note="Not applicable to banks.")
    model = Z_ORIGINAL if company_type == "manufacturer" else Z_DOUBLE_PRIME
    r = AltmanResult(applicable=True, model=model)

    need = ["current_assets", "current_liabilities", "total_assets", "retained_earnings",
            "operating_profit", "total_liabilities"]
    need += ["revenue", "shares_outstanding"] if model is Z_ORIGINAL else ["total_equity"]
    r.missing = [label_of(k) for k in need if cur.get(k) is None]
    if model is Z_ORIGINAL and share_price is None:
        r.missing.append("Share price (assumption)")
    if r.missing:
        return r
    ta, tl = cur["total_assets"], cur["total_liabilities"]
    if ta == 0 or tl == 0:
        r.note = "Not defined: total assets or total liabilities is zero."
        return r

    x = {
        "X1": F(cur["current_assets"] - cur["current_liabilities"], ta),
        "X2": F(cur["retained_earnings"], ta),
        "X3": F(cur["operating_profit"], ta),
    }
    if model is Z_ORIGINAL:
        x["X4"] = F(share_price) * cur["shares_outstanding"] / tl
        x["X5"] = F(cur["revenue"], ta)
    else:
        x["X4"] = F(cur["total_equity"], tl)
    r.components = x
    r.z = sum(c * v for c, v in zip(model.coefficients, x.values()))
    r.zone = zone_for(r.z, model)
    return r
