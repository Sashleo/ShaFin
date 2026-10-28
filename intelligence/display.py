"""
intelligence/display.py - Rounding happens here and only here, for display.

Values are exact Fractions until they are shown. Rounding is half away from zero
to the stated number of places.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Context, Decimal
from fractions import Fraction

_CTX = Context(prec=60)


def to_decimal(value, places: int) -> Decimal:
    f = Fraction(value)
    d = _CTX.divide(Decimal(f.numerator), Decimal(f.denominator))
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP, context=_CTX)


def fmt(value, unit: str) -> str:
    """Format a value: pct, x, days, pkr (whole rupees), per_share (rupees), score,
    one or two (decimal places); anything else to four places."""
    if value is None:
        return "—"
    if unit == "pct":
        return f"{to_decimal(Fraction(value) * 100, 2):,}%"
    if unit == "x":
        return f"{to_decimal(value, 2):,}x"
    if unit == "days":
        return f"{to_decimal(value, 1):,} days"
    if unit == "pkr":
        return f"PKR {to_decimal(value, 0):,}"
    if unit == "per_share":
        return f"PKR {to_decimal(value, 2):,}"
    if unit == "score":
        return f"{to_decimal(value, 2)}"
    if unit == "one":
        return f"{to_decimal(value, 1)}"
    if unit == "two":
        return f"{to_decimal(value, 2)}"
    return f"{to_decimal(value, 4)}"
