"""
Demo mode: four fictional companies, one of them a bank, loaded as entered figures
through the real save paths; every statement in them adds up.
"""

import json
from pathlib import Path

import pytest

from database.analyses import get_analysis, list_analyses
from database.companies import get_company, list_companies
from demo.loader import DATA_FILE, DEMO_PASSWORD, ensure_demo_owner, load_demo_companies
from routers.analyser import run_analysis

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def demo(db):
    ensure_demo_owner()
    assert load_demo_companies() == 4
    return list_companies()


def _results(companies):
    for c in companies:
        for a in list_analyses(c["id"]):
            yield c, run_analysis(get_analysis(a["id"]), get_company(c["id"]))


def test_three_or_four_fictional_companies_with_one_bank(demo):
    assert len(demo) == 4
    assert [c["company_type"] for c in demo].count("bank") == 1
    for c in demo:
        assert any(w in c["name"] for w in ("Example", "Sample", "Demo", "Illustrative")), c["name"]
        assert "(fictional)" in c["industry"]


def test_every_demo_statement_adds_up(demo):
    for c, r in _results(demo):
        for check in r.checks:
            assert check.passed is True, f"{c['name']}: {check.label} {check.difference} {check.missing}"


def test_profit_bridges_close(demo):
    for c, r in _results(demo):
        assert r.bridge.components, c["name"]
        assert r.bridge.total == r.bridge.end - r.bridge.start


def test_demo_shows_each_model(demo):
    by_name = {c["name"]: r for c, r in _results(demo)}
    spin = by_name["Example Spinning Mills Ltd"]
    assert spin.dcf.computed and spin.altman.zone == "grey"
    assert by_name["Sample Logistics Services Ltd"].dcf.computed
    cement = by_name["Illustrative Cement Works Ltd"]
    assert cement.altman.zone == "distress"
    assert not cement.dcf.computed and cement.dcf.missing        # shows "Required: ..."
    bank = by_name["Demo Commercial Bank Ltd"]
    assert bank.dcf is None and not bank.altman.applicable
    assert all(m.computed for m in bank.valuation)


def test_assumptions_carry_a_source_and_date(demo, db):
    rows = db.execute("SELECT source, as_of FROM assumptions").fetchall()
    assert rows and all(r["source"] == "Demo assumption (fictional)" and r["as_of"] for r in rows)


def test_loading_twice_adds_nothing(demo):
    assert load_demo_companies() == 0
    assert len(list_companies()) == 4


def test_demo_login_works(client, db):
    ensure_demo_owner()
    r = client.post("/login", data={"username": "admin", "password": DEMO_PASSWORD},
                    follow_redirects=False)
    assert r.status_code == 302 and "shafin_session" in r.cookies


def test_banner_and_demo_login_are_shown_in_demo_mode(client, monkeypatch, db):
    from routers.common import templates
    monkeypatch.setitem(templates.env.globals, "DEMO_MODE", True)
    monkeypatch.setitem(templates.env.globals, "demo_password", DEMO_PASSWORD)
    ensure_demo_owner()
    page = client.get("/login").text
    assert "Demo mode" in page and DEMO_PASSWORD in page


def test_no_banner_outside_demo_mode(client, owner):
    assert "Demo mode" not in client.get("/login").text


def test_demo_data_file_states_it_is_fictional():
    assert "fictional" in json.loads(DATA_FILE.read_text(encoding="utf-8"))["_note"].lower()


def test_demo_compose_turns_on_demo_mode_with_its_own_volume():
    text = (ROOT / "docker-compose.demo.yml").read_text(encoding="utf-8")
    assert 'DEMO_MODE: "true"' in text and "shafin_demo_data" in text
    assert "127.0.0.1:${SHAFIN_PORT:-8001}:8000" in text          # never clashes with 8000
