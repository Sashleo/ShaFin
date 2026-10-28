"""
Altman Z-scores. Variants, coefficients, cut-offs and citations: docs/CALCULATIONS.md.

Non-manufacturer, Z'' (Altman 2000), from the ratio vector's company:
| input        | working                              | value   |
|--------------|--------------------------------------|---------|
| X1           | (300,000 - 200,000) / 800,000         | 0.125   |
| X2           | 150,000 / 800,000                     | 0.1875  |
| X3           | 150,000 / 800,000                     | 0.1875  |
| X4           | 400,000 / 400,000 (book equity / TL)  | 1.0     |
| Z''          | 6.56(0.125) + 3.26(0.1875)            |         |
|              |  + 6.72(0.1875) + 1.05(1.0)           |         |
|              | = 0.82 + 0.61125 + 1.26 + 1.05        | 3.74125 |
Zone: above 2.60, safe.

Manufacturer, original Z (Altman 1968), share price 60, 10,000 shares:
| input        | working                              | value   |
|--------------|--------------------------------------|---------|
| X1, X2, X3   | as above                              |         |
| X4           | (60 x 10,000) / 400,000               | 1.5     |
| X5           | 1,000,000 / 800,000                   | 1.25    |
| Z            | 1.2(0.125) + 1.4(0.1875) + 3.3(0.1875)|         |
|              |  + 0.6(1.5) + 1.0(1.25)               |         |
|              | = 0.15 + 0.2625 + 0.61875 + 0.9 + 1.25| 3.18125 |
Zone: above 2.99, safe.

Zone boundaries, with X1 = X2 = X3 (= X5) = 0 so the score is one term:
| model | score    | built from                                     | zone     |
|-------|----------|------------------------------------------------|----------|
| Z''   | 2.60     | 1.05 x 52,000/21,000                           | grey     |
| Z''   | 2.6000.. | 1.05 x 52,001/21,000                           | safe     |
| Z''   | 1.10     | 1.05 x 22,000/21,000                           | grey     |
| Z''   | 1.0999.. | 1.05 x 21,999/21,000                           | distress |
| Z     | 2.99     | 0.6 x (299 x 1,000)/60,000                     | grey     |
| Z     | 2.99001  | 0.6 x (299.001 x 1,000)/60,000                 | safe     |
| Z     | 1.81     | 0.6 x (181 x 1,000)/60,000                     | grey     |
| Z     | 1.80999  | 0.6 x (180.999 x 1,000)/60,000                 | distress |
"""

from fractions import Fraction as F

import pytest

from intelligence.altman import Z_DOUBLE_PRIME, Z_ORIGINAL, compute_altman, zone_for

BASE = {"current_assets": 300_000, "current_liabilities": 200_000, "total_assets": 800_000,
        "retained_earnings": 150_000, "operating_profit": 150_000, "total_liabilities": 400_000,
        "total_equity": 400_000, "revenue": 1_000_000, "shares_outstanding": 10_000}


def test_coefficients_and_cut_offs():
    assert Z_DOUBLE_PRIME.coefficients == (F("6.56"), F("3.26"), F("6.72"), F("1.05"))
    assert (Z_DOUBLE_PRIME.safe_above, Z_DOUBLE_PRIME.distress_below) == (F("2.60"), F("1.10"))
    assert Z_ORIGINAL.coefficients == (F("1.2"), F("1.4"), F("3.3"), F("0.6"), F("1.0"))
    assert (Z_ORIGINAL.safe_above, Z_ORIGINAL.distress_below) == (F("2.99"), F("1.81"))
    assert "1968" in Z_ORIGINAL.citation and "2000" in Z_DOUBLE_PRIME.citation


def test_z_double_prime_hand_vector():
    r = compute_altman("non_manufacturer", BASE)
    assert r.model is Z_DOUBLE_PRIME
    assert r.components == {"X1": F("0.125"), "X2": F("0.1875"), "X3": F("0.1875"), "X4": F(1)}
    assert r.z == F("3.74125") and r.zone == "safe"


def test_z_double_prime_has_no_constant():
    """The +3.25 belongs to the emerging-market score, not to Z''."""
    zero = dict(BASE, current_assets=200_000, retained_earnings=0, operating_profit=0,
                total_equity=0)
    assert compute_altman("non_manufacturer", zero).z == 0


def test_original_z_hand_vector():
    r = compute_altman("manufacturer", BASE, share_price=F(60))
    assert r.model is Z_ORIGINAL
    assert r.components == {"X1": F("0.125"), "X2": F("0.1875"), "X3": F("0.1875"),
                            "X4": F("1.5"), "X5": F("1.25")}
    assert r.z == F("3.18125") and r.zone == "safe"


def _zpp(equity):
    facts = dict(BASE, current_assets=1, current_liabilities=1, retained_earnings=0,
                 operating_profit=0, total_liabilities=21_000, total_equity=equity,
                 total_assets=21_000 + equity)
    return compute_altman("non_manufacturer", facts)


@pytest.mark.parametrize("equity, z, zone", [
    (52_000, F("2.60"), "grey"),
    (52_001, F("1.05") * F(52_001, 21_000), "safe"),
    (22_000, F("1.10"), "grey"),
    (21_999, F("1.05") * F(21_999, 21_000), "distress"),
])
def test_z_double_prime_zone_boundaries(equity, z, zone):
    r = _zpp(equity)
    assert r.z == z and r.zone == zone


def _z(price):
    facts = dict(BASE, current_assets=1, current_liabilities=1, retained_earnings=0,
                 operating_profit=0, revenue=0, total_liabilities=60_000, shares_outstanding=1_000)
    return compute_altman("manufacturer", facts, share_price=F(price))


@pytest.mark.parametrize("price, z, zone", [
    ("299", F("2.99"), "grey"),
    ("299.001", F("2.99001"), "safe"),
    ("181", F("1.81"), "grey"),
    ("180.999", F("1.80999"), "distress"),
])
def test_original_z_zone_boundaries(price, z, zone):
    r = _z(price)
    assert r.z == z and r.zone == zone


def test_zone_for_is_strict_at_both_cut_offs():
    assert zone_for(F("2.60"), Z_DOUBLE_PRIME) == "grey"
    assert zone_for(F("1.10"), Z_DOUBLE_PRIME) == "grey"
    assert zone_for(F("2.99"), Z_ORIGINAL) == "grey"
    assert zone_for(F("1.81"), Z_ORIGINAL) == "grey"


@pytest.mark.parametrize("key", ["current_assets", "current_liabilities", "total_assets",
                                 "retained_earnings", "operating_profit", "total_liabilities",
                                 "total_equity"])
def test_z_double_prime_needs_every_input(key):
    facts = dict(BASE)
    del facts[key]
    r = compute_altman("non_manufacturer", facts)
    assert r.z is None and r.zone == "" and len(r.missing) == 1


@pytest.mark.parametrize("key", ["revenue", "shares_outstanding", "total_liabilities"])
def test_original_z_needs_every_input(key):
    facts = dict(BASE)
    del facts[key]
    r = compute_altman("manufacturer", facts, share_price=F(60))
    assert r.z is None and len(r.missing) == 1


def test_original_z_needs_the_share_price():
    r = compute_altman("manufacturer", BASE)
    assert r.z is None and r.missing == ["Share price (assumption)"]


def test_not_applicable_to_banks():
    r = compute_altman("bank", BASE, share_price=F(60))
    assert not r.applicable and r.z is None and r.note == "Not applicable to banks."


def test_zero_total_liabilities_is_not_defined():
    r = compute_altman("non_manufacturer", dict(BASE, total_liabilities=0))
    assert r.z is None and "Not defined" in r.note
