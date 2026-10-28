"""
Units: Rupees, Thousand, Lakh, Million, Crore and Billion convert to whole rupees
exactly, with integer arithmetic. Hand-computed:

| typed                 | unit      | factor        | whole rupees                    |
|-----------------------|-----------|---------------|---------------------------------|
| 1                     | Rupees    | 1             | 1                               |
| 1,234                 | Thousand  | 1,000         | 1,234,000                       |
| 3                     | Lakh      | 100,000       | 300,000                         |
| 2.5                   | Million   | 1,000,000     | 2,500,000                       |
| 1.5                   | Crore     | 10,000,000    | 15,000,000                      |
| 1.234567891           | Billion   | 1,000,000,000 | 1,234,567,891                   |
| (12.3)                | Thousand  | 1,000         | -12,300                         |
| -7                    | Lakh      | 100,000       | -700,000                        |
| 0.001                 | Thousand  | 1,000         | 1                               |
| 0.00125               | Lakh      | 100,000       | 125                             |
| 123456789012345.678   | Million   | 1,000,000     | 123,456,789,012,345,678,000     |
The last row is beyond 2^53, where a float would lose digits.
"""

import pytest

from intelligence.units import UNITS, UnitError, format_rupees, from_rupees, parse_number, to_rupees


@pytest.mark.parametrize("typed, unit, rupees", [
    ("1", "rupees", 1),
    ("1,234", "thousand", 1_234_000),
    ("3", "lakh", 300_000),
    ("2.5", "million", 2_500_000),
    ("1.5", "crore", 15_000_000),
    ("1.234567891", "billion", 1_234_567_891),
    ("(12.3)", "thousand", -12_300),
    ("-7", "lakh", -700_000),
    ("0.001", "thousand", 1),
    ("0.00125", "lakh", 125),
    ("123456789012345.678", "million", 123_456_789_012_345_678_000),
    (" 1 000 ", "rupees", 1_000),
    ("0", "billion", 0),
])
def test_conversion_to_whole_rupees(typed, unit, rupees):
    assert to_rupees(typed, unit) == rupees
    assert isinstance(to_rupees(typed, unit), int)


def test_the_six_units_and_their_factors():
    assert {k: v[1] for k, v in UNITS.items()} == {
        "rupees": 1, "thousand": 1_000, "lakh": 100_000, "million": 1_000_000,
        "crore": 10_000_000, "billion": 1_000_000_000,
    }


@pytest.mark.parametrize("typed, unit", [
    ("12.34", "rupees"),        # 12.34 rupees is not whole
    ("0.0001", "thousand"),     # 0.1 rupee
    ("1.0000000001", "billion"),
    ("0.000001", "lakh"),       # 0.1 rupee
])
def test_fractions_of_a_rupee_are_refused_not_rounded(typed, unit):
    with pytest.raises(UnitError, match="not a whole number of rupees"):
        to_rupees(typed, unit)


@pytest.mark.parametrize("typed", ["abc", "1e6", "--1", "(-1)", "1.2.3", "", "1,23.4.5", "nan", "inf"])
def test_non_numbers_are_refused(typed):
    with pytest.raises(UnitError):
        to_rupees(typed, "thousand")


def test_unknown_unit_is_refused():
    with pytest.raises(UnitError):
        to_rupees("1", "dozen")


@pytest.mark.parametrize("rupees, unit, text", [
    (1_234_000, "thousand", "1234"),
    (2_500_000, "million", "2.5"),
    (125, "lakh", "0.00125"),
    (-12_300, "thousand", "-12.3"),
    (15_000_000, "crore", "1.5"),
    (1, "billion", "0.000000001"),
])
def test_from_rupees_is_the_exact_inverse(rupees, unit, text):
    assert from_rupees(rupees, unit) == text
    assert to_rupees(text, unit) == rupees


def test_parse_number_is_exact():
    from fractions import Fraction
    assert parse_number("15.2") == Fraction(76, 5)
    assert parse_number("(0.5)") == Fraction(-1, 2)


def test_format_rupees():
    assert format_rupees(1_234_567) == "PKR 1,234,567"
    assert format_rupees(None) == "—"
