"""
Bank ratios, hand-computed. Fictional bank, whole rupees.

| figure                          | current | prior |
|---------------------------------|---------|-------|
| net mark-up income              |    500  |       |
| non mark-up income              |    200  |       |
| operating expenses              |    350  |       |
| profit after tax                |    180  |       |
| gross advances                  |  4,000  |       |
| provisions held against advances|    240  |       |
| NPLs                            |    300  |       |
| deposits                        |  8,000  |       |
| CASA deposits                   |  5,600  |       |
| earning assets                  |  9,000  | 8,000 |
| total assets                    | 10,000  | 9,000 |
| total equity                    |    800  |       |
| CAR as reported                 | 15.25%  |       |
| shares outstanding              |    100  |       |
Share price (assumption): 9.

| ratio               | working                              | value       |
|---------------------|--------------------------------------|-------------|
| NIM (earning assets)| 500 / ((9,000 + 8,000) / 2)          | 1/17        |
| NIM (total assets)  | 500 / ((10,000 + 9,000) / 2)         | 1/19        |
| cost to income      | 350 / (500 + 200)                    | 0.5         |
| ROE                 | 180 / 800                            | 0.225       |
| ROA                 | 180 / 10,000                         | 0.018       |
| advances to deposits| 4,000 / 8,000                        | 0.5         |
| CASA share          | 5,600 / 8,000                        | 0.7         |
| NPL ratio           | 300 / 4,000                          | 0.075       |
| coverage            | 240 / 300                            | 0.8         |
| equity to assets    | 800 / 10,000                         | 0.08        |
| CAR as reported     | 15.25 / 100                          | 0.1525      |
| EPS                 | 180 / 100                            | 1.8         |
| book value / share  | 800 / 100                            | 8           |
| P/B                 | 9 / 8                                | 1.125       |
| P/E                 | 9 / 1.8                              | 5           |
"""

from fractions import Fraction as F

import pytest

from intelligence.bank import compute_bank_ratios, compute_bank_valuation, compute_nim

CUR = {"net_markup_income": 500, "non_markup_income": 200, "operating_expenses": 350,
       "profit_after_tax": 180, "gross_advances": 4_000, "advance_provisions": 240, "npls": 300,
       "deposits": 8_000, "casa_deposits": 5_600, "earning_assets": 9_000, "total_assets": 10_000,
       "total_equity": 800, "car_reported": F("0.1525"), "car_reported_page": "41",
       "shares_outstanding": 100}
PRIOR = {"earning_assets": 8_000, "total_assets": 9_000}

EXPECTED = {
    "nim": F(1, 17), "cost_to_income": F("0.5"), "roe": F("0.225"), "roa": F("0.018"),
    "advances_to_deposits": F("0.5"), "casa_share": F("0.7"), "npl_ratio": F("0.075"),
    "coverage": F("0.8"), "equity_to_assets": F("0.08"), "car_reported": F("0.1525"),
    "eps": F("1.8"),
}


def _ratios(cur=CUR, prior=PRIOR):
    return {m.key: m for m in compute_bank_ratios(cur, prior)}


@pytest.mark.parametrize("key", EXPECTED)
def test_hand_computed_bank_ratio(key):
    assert _ratios()[key].value == EXPECTED[key]


def test_every_bank_ratio_has_a_vector():
    assert set(_ratios()) == set(EXPECTED)


def test_nim_states_its_basis():
    m = compute_nim(CUR, PRIOR)
    assert "average earning assets" in m.note


def test_nim_uses_average_total_assets_when_earning_assets_are_not_entered():
    m = compute_nim(CUR, {"total_assets": 9_000})
    assert m.value == F(1, 19)
    assert "average total assets" in m.note and "not entered" in m.note
    assert m.formula == "Net mark-up income / Average total assets"


def test_nim_needs_a_prior_year_base():
    m = compute_nim(CUR, {})
    assert m.value is None and m.missing


def test_car_is_shown_as_reported_with_its_page():
    car = _ratios()["car_reported"]
    assert car.value == F("0.1525") and "page 41" in car.note


def test_coverage_with_no_npls_is_not_defined():
    m = _ratios(dict(CUR, npls=0))["coverage"]
    assert m.value is None and m.note == "Not defined: NPLs are zero."


def test_casa_is_optional_and_named_when_missing():
    cur = dict(CUR)
    del cur["casa_deposits"]
    m = _ratios(cur)["casa_share"]
    assert m.value is None and m.missing == ["Current and savings deposits (CASA), if disclosed"]


def test_price_to_book_and_price_to_earnings():
    v = {m.key: m for m in compute_bank_valuation(CUR, F(9))}
    assert v["book_value_per_share"].value == 8
    assert v["pb"].value == F("1.125")
    assert v["pe"].value == 5


def test_pe_with_a_loss_is_not_defined():
    v = {m.key: m for m in compute_bank_valuation(dict(CUR, profit_after_tax=-5), F(9))}
    assert v["pe"].value is None and "negative" in v["pe"].note


def test_valuation_needs_the_share_price():
    v = {m.key: m for m in compute_bank_valuation(CUR, None)}
    assert v["pb"].missing == ["share price"] and v["pe"].missing == ["share price"]
    assert v["book_value_per_share"].value == 8
