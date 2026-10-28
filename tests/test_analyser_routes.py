"""The Analyser through HTTP: companies, analyses, figures in any unit, history."""

from fractions import Fraction

from database.analyses import fact_history, load_facts


def _setup(client, company_type="manufacturer", unit="thousand"):
    r = client.post("/analyser/companies", data={"name": "Fictional Route Co",
                                                 "company_type": company_type}, follow_redirects=False)
    assert r.status_code == 303
    cid = r.headers["location"].rsplit("/", 1)[1]
    r = client.post(f"/analyser/c/{cid}/analyses", data={
        "name": "Annual", "current_label": "FY2025", "prior_label": "FY2024", "unit": unit},
        follow_redirects=False)
    return cid, r.headers["location"].rsplit("/", 1)[1]


def test_pages_need_login(client):
    assert client.get("/analyser", headers={"accept": "application/json"}).status_code == 401


def test_company_needs_a_type(logged_in):
    r = logged_in.post("/analyser/companies", data={"name": "Typeless"}, follow_redirects=False)
    assert "error=" in r.headers["location"]


def test_figures_are_stored_in_whole_rupees(logged_in):
    _, aid = _setup(logged_in)
    r = logged_in.post(f"/analyser/a/{aid}/facts", data={
        "unit": "thousand", "current:revenue": "1,234.5", "prior:revenue": "(20)",
        "current:shares_outstanding": "1000000"}, follow_redirects=False)
    assert r.status_code == 303
    facts = load_facts(aid)
    assert facts["current"]["revenue"] == 1_234_500
    assert facts["prior"]["revenue"] == -20_000
    assert facts["current"]["shares_outstanding"] == 1_000_000      # counts are not scaled


def test_a_fraction_of_a_rupee_is_refused_and_named(logged_in):
    _, aid = _setup(logged_in, unit="thousand")
    r = logged_in.post(f"/analyser/a/{aid}/facts", data={
        "unit": "thousand", "current:revenue": "1.2345", "current:cost_of_sales": "500"})
    assert r.status_code == 422
    assert "not a whole number of rupees" in r.text
    facts = load_facts(aid)
    assert "revenue" not in facts["current"] and facts["current"]["cost_of_sales"] == 500_000


def test_unit_change_reinterprets_the_typed_numbers(logged_in):
    _, aid = _setup(logged_in, unit="thousand")
    logged_in.post(f"/analyser/a/{aid}/facts", data={"unit": "crore", "current:revenue": "2.5"})
    assert load_facts(aid)["current"]["revenue"] == 25_000_000
    page = logged_in.get(f"/analyser/a/{aid}").text
    assert 'value="2.5"' in page and 'value="crore" data-factor="10000000" selected' in page


def test_bank_car_needs_a_page_reference(logged_in):
    _, aid = _setup(logged_in, company_type="bank")
    r = logged_in.post(f"/analyser/a/{aid}/facts", data={"unit": "thousand",
                                                         "current:car_reported": "15.2"})
    assert r.status_code == 422 and "page" in r.text
    logged_in.post(f"/analyser/a/{aid}/facts", data={"unit": "thousand",
                                                     "current:car_reported": "15.2",
                                                     "current:car_reported_page": "48"})
    facts = load_facts(aid)["current"]
    assert facts["car_reported"] == Fraction(152, 1000)
    assert facts["car_reported_page"] == "48"


def test_every_change_is_in_the_history(logged_in):
    _, aid = _setup(logged_in)
    for value in ("100", "150", ""):
        logged_in.post(f"/analyser/a/{aid}/facts", data={"unit": "thousand", "current:revenue": value})
    h = fact_history(aid, "current", "revenue")
    assert [(x["previous"], x["new"]) for x in h] == [(None, 100_000), (100_000, 150_000), (150_000, None)]
    assert all(x["by"] == "admin" for x in h)


def test_unchanged_figures_write_no_history(logged_in):
    _, aid = _setup(logged_in)
    for _ in range(2):
        logged_in.post(f"/analyser/a/{aid}/facts", data={"unit": "thousand", "current:revenue": "100"})
    assert len(fact_history(aid, "current", "revenue")) == 1


def test_analysis_page_shows_required_inputs_not_guesses(logged_in):
    _, aid = _setup(logged_in)
    page = logged_in.get(f"/analyser/a/{aid}").text
    assert "Required: Risk-free rate (assumption)" in page
    assert "The DCF does not run until these are entered" in page


def test_user_text_is_escaped(logged_in):
    r = logged_in.post("/analyser/companies", data={"name": "<script>alert(1)</script>",
                                                    "company_type": "bank"}, follow_redirects=True)
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text
