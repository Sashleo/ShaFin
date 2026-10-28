"""
No default and no fallback for any rate: assumptions are entered per analysis with a
required source and date; the DCF names what is missing instead of guessing.
"""

from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

import pytest

from database.analyses import create_analysis, load_assumptions, save_assumptions
from database.companies import create_company
from intelligence.dcf import compute_dcf

ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today().isoformat()


@pytest.fixture
def analysis(owner):
    c = create_company("Fictional Assumptions Co", "non_manufacturer", None, "admin")
    return create_analysis(c["id"], "FY", "FY2025", "FY2024", "thousand", "admin")


def test_value_source_and_date_are_saved(analysis):
    errors = save_assumptions(analysis, {"risk_free_rate": ("12.5", "Auction result", TODAY)}, "admin")
    assert errors == {}
    a = load_assumptions(analysis)["risk_free_rate"]
    assert a["value"] == Fraction(1, 8) and a["source"] == "Auction result" and a["as_of"] == TODAY
    assert a["saved_by"] == "admin"


@pytest.mark.parametrize("source, as_of, message", [
    ("", TODAY, "source"),
    ("Note 12", "", "YYYY-MM-DD"),
    ("Note 12", "25/10/2026", "YYYY-MM-DD"),
    ("Note 12", (date.today() + timedelta(days=1)).isoformat(), "future"),
])
def test_source_and_a_real_date_are_required(analysis, source, as_of, message):
    errors = save_assumptions(analysis, {"beta": ("1.1", source, as_of)}, "admin")
    assert message in errors["beta"]
    assert "beta" not in load_assumptions(analysis)


def test_out_of_range_values_are_refused(analysis):
    errors = save_assumptions(analysis, {"debt_weight": ("120", "Target structure", TODAY),
                                         "forecast_years": ("2.5", "Choice", TODAY)}, "admin")
    assert set(errors) == {"debt_weight", "forecast_years"}


def test_changes_are_audited_with_previous_and_new(db, analysis):
    save_assumptions(analysis, {"beta": ("1.1", "Regression", TODAY)}, "admin")
    save_assumptions(analysis, {"beta": ("1.2", "Regression", TODAY)}, "admin")
    save_assumptions(analysis, {"beta": ("", "", "")}, "admin")
    rows = [r["details"] for r in db.execute(
        "SELECT details FROM audit_log WHERE event_type = 'assumption_changed' ORDER BY id")]
    assert len(rows) == 3
    assert '"previous": null' in rows[0] and '"value": "1.1"' in rows[0]
    assert '"value": "1.1"' in rows[1] and '"value": "1.2"' in rows[1]
    assert '"new": null' in rows[2]


def test_dcf_with_no_assumptions_names_every_required_one():
    facts = {"revenue": 1000, "cash": 10, "short_term_borrowings": 0, "long_term_borrowings": 0,
             "shares_outstanding": 10}
    r = compute_dcf(facts, {}, {})
    assert not r.computed
    for label in ("Risk-free rate", "Equity risk premium", "Beta", "Corporate tax rate",
                  "Terminal growth", "Forecast years", "Debt weight in WACC"):
        assert any(m.startswith(label) for m in r.missing), label


def _assumptions(**overrides):
    a = {"risk_free_rate": Fraction(1, 10), "equity_risk_premium": Fraction(5, 100),
         "beta": Fraction(1), "tax_rate": Fraction(3, 10), "terminal_growth": Fraction(2, 100),
         "forecast_years": Fraction(1), "debt_weight": Fraction(1, 2), "revenue_growth": Fraction(0),
         "ebit_margin": Fraction(1, 10), "da_pct_revenue": Fraction(0),
         "capex_pct_revenue": Fraction(0), "nwc_pct_revenue": Fraction(0)}
    a.update(overrides)
    return a


def test_cost_of_debt_is_computed_from_finance_cost_when_not_entered():
    cur = {"revenue": 1000, "cash": 0, "short_term_borrowings": 100, "long_term_borrowings": 300,
           "finance_cost": 36, "shares_outstanding": 10}
    prior = {"short_term_borrowings": 100, "long_term_borrowings": 100}
    r = compute_dcf(cur, prior, _assumptions())
    # average borrowings = (400 + 200) / 2 = 300; 36 / 300 = 12%
    assert r.cost_of_debt == Fraction(12, 100)
    assert "finance cost / average borrowings" in r.cost_of_debt_basis


def test_an_entered_cost_of_debt_is_used_as_is():
    cur = {"revenue": 1000, "cash": 0, "short_term_borrowings": 100, "long_term_borrowings": 300,
           "shares_outstanding": 10}
    r = compute_dcf(cur, {}, _assumptions(cost_of_debt=Fraction(9, 100)))
    assert r.computed and r.cost_of_debt == Fraction(9, 100)
    assert r.cost_of_debt_basis == "Entered as an assumption."


def test_without_cost_of_debt_or_its_inputs_the_dcf_names_them():
    cur = {"revenue": 1000, "cash": 0, "short_term_borrowings": 100, "long_term_borrowings": 300,
           "shares_outstanding": 10}
    r = compute_dcf(cur, {}, _assumptions())
    msg = next(m for m in r.missing if m.startswith("Cost of debt"))
    assert "Finance cost" in msg and "Prior-year short-term borrowings" in msg


def test_zero_average_debt_is_not_divided_by_one():
    cur = {"revenue": 1000, "cash": 0, "short_term_borrowings": 0, "long_term_borrowings": 0,
           "finance_cost": 5, "shares_outstanding": 10}
    prior = {"short_term_borrowings": 0, "long_term_borrowings": 0}
    r = compute_dcf(cur, prior, _assumptions())
    assert any("average borrowings are zero" in m for m in r.missing)
    assert r.cost_of_debt is None


def test_settings_keeps_no_rates():
    text = (ROOT / "routers" / "settings.py").read_text(encoding="utf-8").lower()
    for word in ("risk_free", "equity_risk_premium", "terminal_growth", "cost_of_debt"):
        assert word not in text
