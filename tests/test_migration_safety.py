"""database/schema.py: migrations are idempotent and never drop or restore rows."""

from database.schema import run_migrations


def _tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_running_migrations_twice_keeps_rows(db, owner):
    before = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    run_migrations()
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == before == 1


def test_schema_tables(db):
    tables = _tables(db)
    for name in ("users", "sessions", "audit_log", "pqc_keys", "companies", "analyses", "facts",
                 "assumptions", "thresholds", "reports"):
        assert name in tables


def test_starting_thresholds_are_written_once(db):
    n = db.execute("SELECT COUNT(*) FROM thresholds").fetchone()[0]
    assert n > 0
    db.execute("DELETE FROM thresholds WHERE metric = 'current_ratio'")
    run_migrations()
    assert db.execute("SELECT COUNT(*) FROM thresholds WHERE metric = 'current_ratio'").fetchone()[0] == 0


def test_every_starting_threshold_has_a_rationale(db):
    for row in db.execute("SELECT metric, rationale FROM thresholds"):
        assert len(row["rationale"]) > 10, row["metric"]


def test_facts_accept_only_entered_figures(db, owner):
    import sqlite3
    import pytest
    from database.analyses import create_analysis
    from database.companies import create_company
    c = create_company("Fictional Co", "manufacturer", None, "admin")
    aid = create_analysis(c["id"], "A", "FY2", "FY1", "thousand", "admin")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO facts (analysis_id, period, field, value_rupees, unit, entered_text, "
                   "source, saved_by, saved_at) VALUES (?, 'current', 'revenue', 1, 'rupees', '1', "
                   "'imported', 'admin', 'now')", (aid,))
