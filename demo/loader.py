"""
demo/loader.py - Demo mode: a demo owner login and four fictional companies.

Runs at startup when DEMO_MODE is true. It creates the owner account with the demo
password (shown on the login page) and loads demo/companies.json through the same
functions a user's entries go through, so the demo exercises the real code paths:
facts are converted to whole rupees, assumptions are saved with a source and date,
and every save is audited. Nothing is loaded if any company already exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from database import analyses as store
from database.companies import create_company
from database.connection import get_db

log = structlog.get_logger()

DEMO_PASSWORD = "shafin-demo-2026"
DEMO_USER = "admin"
DEMO_SOURCE = "Demo assumption (fictional)"
DEMO_AS_OF = "2026-06-30"
DATA_FILE = Path(__file__).with_name("companies.json")


def ensure_demo_owner() -> None:
    db = get_db()
    if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return
    from routers.auth import _create_admin
    _create_admin(db, DEMO_PASSWORD)
    log.info("Demo owner created")


def load_demo_companies() -> int:
    """Load the fictional companies once. Returns how many were loaded."""
    if get_db().execute("SELECT 1 FROM companies LIMIT 1").fetchone():
        return 0
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    for c in data["companies"]:
        company = create_company(c["name"], c["company_type"], c["industry"], DEMO_USER)
        for a in c["analyses"]:
            aid = store.create_analysis(company["id"], a["name"], a["current_label"],
                                        a["prior_label"], a["unit"], DEMO_USER)
            entries = {(period, field): value
                       for period, figures in a["facts"].items()
                       for field, value in figures.items()}
            errors = store.save_facts(aid, a["unit"], entries, DEMO_USER)
            if errors:
                raise ValueError(f"demo figures for {c['name']} did not save: {errors}")
            errors = store.save_assumptions(
                aid, {k: (v, DEMO_SOURCE, DEMO_AS_OF) for k, v in a["assumptions"].items()},
                DEMO_USER)
            if errors:
                raise ValueError(f"demo assumptions for {c['name']} did not save: {errors}")
    log.info("Demo companies loaded", count=len(data["companies"]))
    return len(data["companies"])
