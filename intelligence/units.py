"""
intelligence/units.py - Reporting units and exact conversion to whole rupees.

Annual reports state figures in Rupees, thousands, lakh, millions, crore or billions.
Every money figure is stored as a whole number of rupees. The conversion uses integer
arithmetic only: the entered text is split into digits, multiplied by the unit's
factor and divided by the power of ten its decimals imply. A value that would need
fractions of a rupee is refused, never rounded.
"""

from __future__ import annotations

import re
from fractions import Fraction

# key -> (label, rupees per unit)
UNITS: dict[str, tuple[str, int]] = {
    "rupees":   ("Rupees", 1),
    "thousand": ("Thousand (Rs '000)", 1_000),
    "lakh":     ("Lakh", 100_000),
    "million":  ("Million", 1_000_000),
    "crore":    ("Crore", 10_000_000),
    "billion":  ("Billion", 1_000_000_000),
}

_NUMBER = re.compile(r"^(-)?(\d+)(?:\.(\d+))?$")


class UnitError(ValueError):
    """The entered text is not a number, or not a whole number of rupees."""


def _split(text: str) -> tuple[int, int, int]:
    """Return (sign, integer formed by all digits, number of decimal places)."""
    s = str(text).strip().replace(",", "").replace(" ", "")
    negative = False
    if s.startswith("(") and s.endswith(")"):        # (1,234) is a negative figure
        negative, s = True, s[1:-1]
    m = _NUMBER.match(s)
    if not m:
        raise UnitError(f"{text!r} is not a number")
    if m.group(1):
        if negative:
            raise UnitError(f"{text!r} is not a number")
        negative = True
    whole, decimals = m.group(2), m.group(3) or ""
    return (-1 if negative else 1), int(whole + decimals), len(decimals)


def parse_number(text: str) -> Fraction:
    """Exact value of a typed number: '12.5' -> 25/2, '(3)' -> -3."""
    sign, digits, places = _split(text)
    return sign * Fraction(digits, 10 ** places)


def to_rupees(text: str, unit: str) -> int:
    """Convert a figure typed in `unit` to whole rupees, exactly."""
    if unit not in UNITS:
        raise UnitError(f"unknown unit {unit!r}")
    sign, digits, places = _split(text)
    scaled = digits * UNITS[unit][1]
    divisor = 10 ** places
    if scaled % divisor:
        raise UnitError(
            f"{text} {UNITS[unit][0]} is not a whole number of rupees; "
            "enter it in a smaller unit"
        )
    return sign * (scaled // divisor)


def from_rupees(rupees: int, unit: str) -> str:
    """Exact decimal text of `rupees` expressed in `unit` (inverse of to_rupees)."""
    factor = UNITS[unit][1]
    sign = "-" if rupees < 0 else ""
    whole, rest = divmod(abs(rupees), factor)
    if not rest:
        return f"{sign}{whole}"
    places = len(str(factor)) - 1                    # every factor is a power of ten
    return f"{sign}{whole}.{str(rest).rjust(places, '0').rstrip('0')}"


def format_rupees(rupees: int | None) -> str:
    """'PKR 1,234,567' for display. None -> '—'."""
    if rupees is None:
        return "—"
    return f"PKR {rupees:,}"
