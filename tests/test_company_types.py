"""
The company type decides fields and models: each type shows only its own fields and
models, switching type keeps entered data, and a bank never runs Altman or the DCF.
"""

from fractions import Fraction

from intelligence.altman import Z_DOUBLE_PRIME, Z_ORIGINAL
from intelligence.analyser import analyse
from intelligence.assumptions import ASSUMPTIONS, assumptions_for
from intelligence.fields import FIELDS, fields_for

# Every field and every assumption entered, so nothing is skipped for lack of input.
ALL_FACTS = {k.key: 1_000 for k in FIELDS}
ALL_FACTS.update(total_assets=10_000, total_liabilities=6_000, total_equity=4_000,
                 car_reported=Fraction(15, 100), shares_outstanding=100)
ALL_ASSUMPTIONS = {a.key: Fraction(1, 10) for a in ASSUMPTIONS}
ALL_ASSUMPTIONS.update(forecast_years=Fraction(3), beta=Fraction(1), terminal_growth=Fraction(2, 100),
                       share_price=Fraction(50))


def _run(company_type):
    return analyse(company_type, {"current": dict(ALL_FACTS), "prior": dict(ALL_FACTS)},
                   ALL_ASSUMPTIONS, [], tolerance=1)


def _keys(company_type):
    return {f.key for f in fields_for(company_type)}


def test_banks_get_their_own_fields():
    bank = _keys("bank")
    for key in ("markup_earned", "markup_expensed", "net_markup_income", "non_markup_income",
                "operating_expenses", "provisions", "profit_before_tax", "profit_after_tax",
                "gross_advances", "advance_provisions", "net_advances", "deposits", "casa_deposits",
                "investments", "npls", "total_assets", "total_equity", "car_reported"):
        assert key in bank, key
    for key in ("revenue", "cost_of_sales", "inventory", "current_assets", "capital_expenditure"):
        assert key not in bank, key


def test_non_banks_do_not_see_bank_fields():
    for t in ("manufacturer", "non_manufacturer"):
        keys = _keys(t)
        assert "revenue" in keys and "total_liabilities" in keys
        assert not keys & {"markup_earned", "deposits", "npls", "car_reported"}


def test_car_asks_for_its_page_reference():
    car = next(f for f in fields_for("bank") if f.key == "car_reported")
    assert car.page_ref and car.kind == "percent"


def test_bank_assumptions_are_only_the_share_price():
    assert [a.key for a in assumptions_for("bank")] == ["share_price"]


def test_a_bank_never_runs_altman_or_the_dcf():
    r = _run("bank")
    assert r.altman.applicable is False and r.altman.z is None
    assert r.altman.note == "Not applicable to banks."
    assert r.dcf is None and r.dupont is None
    assert {m.key for m in r.valuation} == {"book_value_per_share", "pb", "pe"}


def test_manufacturers_get_the_original_z():
    r = _run("manufacturer")
    assert r.altman.model is Z_ORIGINAL and r.altman.z is not None
    assert r.dcf is not None and r.dcf.computed


def test_non_manufacturers_get_z_double_prime():
    r = _run("non_manufacturer")
    assert r.altman.model is Z_DOUBLE_PRIME and r.altman.z is not None
    assert "X5" not in r.altman.components


def test_bank_metrics_are_bank_ratios():
    keys = {m.key for m in _run("bank").metrics}
    assert {"nim", "cost_to_income", "npl_ratio", "coverage", "casa_share", "car_reported"} <= keys
    assert "gross_margin" not in keys


# ── Through the web layer ────────────────────────────────────────────────────

def _company_with_figures(client, company_type):
    r = client.post("/analyser/companies", data={"name": "Fictional Switch Co",
                                                 "company_type": company_type}, follow_redirects=False)
    cid = r.headers["location"].rsplit("/", 1)[1]
    r = client.post(f"/analyser/c/{cid}/analyses", data={
        "name": "FY", "current_label": "FY2025", "prior_label": "FY2024", "unit": "thousand"},
        follow_redirects=False)
    aid = r.headers["location"].rsplit("/", 1)[1]
    client.post(f"/analyser/a/{aid}/facts", data={"unit": "thousand", "current:revenue": "1,250",
                                                  "current:total_assets": "9000"})
    return cid, aid


def test_switching_type_keeps_entered_data(logged_in, db):
    cid, aid = _company_with_figures(logged_in, "manufacturer")
    logged_in.post(f"/analyser/c/{cid}/edit", data={"name": "Fictional Switch Co",
                                                     "company_type": "bank"})
    page = logged_in.get(f"/analyser/a/{aid}").text
    assert 'name="current:revenue"' not in page          # hidden for a bank
    assert 'name="current:total_assets"' in page          # shared field still shown
    assert 'id="dcf"' not in page and "not applicable to banks" in page
    stored = db.execute("SELECT value_rupees FROM facts WHERE analysis_id = ? AND field = 'revenue'",
                        (aid,)).fetchone()
    assert stored["value_rupees"] == 1_250_000             # kept, not deleted

    logged_in.post(f"/analyser/c/{cid}/edit", data={"name": "Fictional Switch Co",
                                                     "company_type": "non_manufacturer"})
    page = logged_in.get(f"/analyser/a/{aid}").text
    assert 'name="current:revenue"' in page and 'value="1250"' in page
    assert 'id="dcf"' in page


def test_type_change_is_audited(logged_in, db):
    cid, _ = _company_with_figures(logged_in, "manufacturer")
    logged_in.post(f"/analyser/c/{cid}/edit", data={"name": "Fictional Switch Co",
                                                     "company_type": "bank"})
    row = db.execute("SELECT details FROM audit_log WHERE event_type = 'company_type_changed'").fetchone()
    assert '"previous": "manufacturer"' in row["details"] and '"new": "bank"' in row["details"]
