"""
database/analyses.py - Analyses, their entered figures (facts) and assumptions.

Every saved change to a figure or an assumption writes an audit event carrying the
previous and new value, who changed it and when; the Data page shows that as the
figure's change history.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from fractions import Fraction
from typing import Optional

from database.connection import get_db
from intelligence.assumptions import ASSUMPTION_BY_KEY, parse_assumption
from intelligence.fields import FIELD_BY_KEY, PERIODS
from intelligence.units import UNITS, UnitError, from_rupees, parse_number, to_rupees
from security.audit import log_event


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Analyses ─────────────────────────────────────────────────────────────────

def create_analysis(company_id: str, name: str, current_label: str, prior_label: str,
                    unit: str, user: str) -> str:
    if unit not in UNITS:
        raise ValueError("Choose a reporting unit.")
    if not name.strip() or not current_label.strip() or not prior_label.strip():
        raise ValueError("Name and both period labels are required.")
    aid, now = uuid.uuid4().hex, _now()
    db = get_db()
    db.execute(
        "INSERT INTO analyses (id, company_id, name, current_label, prior_label, unit, "
        "created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, company_id, name.strip()[:120], current_label.strip()[:20],
         prior_label.strip()[:20], unit, user, now, now),
    )
    db.commit()
    log_event(db, "analysis_created", user, company_id=company_id,
              details={"analysis_id": aid, "name": name.strip()})
    return aid


def get_analysis(analysis_id: str) -> Optional[dict]:
    row = get_db().execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    return dict(row) if row else None


def list_analyses(company_id: str) -> list[dict]:
    rows = get_db().execute(
        "SELECT * FROM analyses WHERE company_id = ? ORDER BY updated_at DESC", (company_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def set_unit(analysis_id: str, unit: str) -> None:
    if unit not in UNITS:
        raise ValueError("Unknown unit.")
    db = get_db()
    db.execute("UPDATE analyses SET unit = ?, updated_at = ? WHERE id = ?",
               (unit, _now(), analysis_id))
    db.commit()


def delete_analysis(analysis_id: str, user: str) -> None:
    a = get_analysis(analysis_id)
    if not a:
        return
    db = get_db()
    if db.execute("SELECT 1 FROM reports WHERE analysis_id = ?", (analysis_id,)).fetchone():
        raise ValueError("This analysis has reports; delete the company to remove them.")
    db.execute("DELETE FROM facts WHERE analysis_id = ?", (analysis_id,))
    db.execute("DELETE FROM assumptions WHERE analysis_id = ?", (analysis_id,))
    db.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    db.commit()
    log_event(db, "analysis_deleted", user, company_id=a["company_id"],
              details={"analysis_id": analysis_id, "name": a["name"]})


def _touch(analysis_id: str) -> None:
    get_db().execute("UPDATE analyses SET updated_at = ? WHERE id = ?", (_now(), analysis_id))


# ── Facts ────────────────────────────────────────────────────────────────────

def _stored(row) -> object:
    """The model value of a facts row: int rupees, int count, or Fraction (percent / 100)."""
    if row["value_rupees"] is not None:
        return int(row["value_rupees"])
    f = FIELD_BY_KEY.get(row["field"])
    value = parse_number(row["value_number"])
    if f is not None and f.kind == "percent":
        return value / 100
    return int(value) if value.denominator == 1 else value


def load_facts(analysis_id: str) -> dict:
    """{"current": {field: value}, "prior": {...}}, plus "<field>_page" for page references."""
    out: dict = {p: {} for p in PERIODS}
    for row in get_db().execute("SELECT * FROM facts WHERE analysis_id = ?", (analysis_id,)):
        out[row["period"]][row["field"]] = _stored(row)
        if row["page_ref"]:
            out[row["period"]][f"{row['field']}_page"] = row["page_ref"]
    return out


def load_form_values(analysis_id: str, unit: str) -> dict:
    """{(period, field): text} in `unit` for the entry form; exact, never rounded."""
    out = {}
    for row in get_db().execute("SELECT * FROM facts WHERE analysis_id = ?", (analysis_id,)):
        if row["value_rupees"] is not None:
            out[(row["period"], row["field"])] = from_rupees(int(row["value_rupees"]), unit)
        else:
            out[(row["period"], row["field"])] = row["value_number"]
        if row["page_ref"]:
            out[(row["period"], row["field"] + "_page")] = row["page_ref"]
    return out


def _parse_fact(field: str, text: str, unit: str) -> tuple[Optional[int], Optional[str]]:
    kind = FIELD_BY_KEY[field].kind
    if kind == "money":
        return to_rupees(text, unit), None
    value = parse_number(text)
    if kind == "count":
        if value.denominator != 1 or value < 0:
            raise UnitError("must be a whole number")
    return None, _decimal_text(value)


def _decimal_text(value: Fraction) -> str:
    """Exact decimal text of a typed number (a terminating decimal): 76/5 -> '15.2'."""
    places = 0
    while (value * 10 ** places).denominator != 1:
        places += 1
    scaled = abs(value.numerator * 10 ** places // value.denominator)
    sign = "-" if value < 0 else ""
    if not places:
        return f"{sign}{scaled}"
    whole, rest = divmod(scaled, 10 ** places)
    return f"{sign}{whole}.{str(rest).rjust(places, '0')}"


def save_facts(analysis_id: str, unit: str, entries: dict, user: str) -> dict:
    """
    entries: {(period, field): text} and {(period, field + "_page"): text}. An empty
    text deletes the figure. Returns {(period, field): error} for figures not saved;
    every other figure is saved and each change is audited.
    """
    a = get_analysis(analysis_id)
    if not a or unit not in UNITS:
        raise ValueError("Unknown analysis or unit.")
    db = get_db()
    existing = {(r["period"], r["field"]): r for r in
                db.execute("SELECT * FROM facts WHERE analysis_id = ?", (analysis_id,))}
    errors, now = {}, _now()

    for (period, field), raw in entries.items():
        if field.endswith("_page") or period not in PERIODS or field not in FIELD_BY_KEY:
            continue
        text = (raw or "").strip()
        page = (entries.get((period, field + "_page")) or "").strip()[:20] or None
        old = existing.get((period, field))
        old_value = None if old is None else _stored(old)
        if not text:
            if old is not None:
                db.execute("DELETE FROM facts WHERE id = ?", (old["id"],))
                _audit_fact(db, a, period, field, old_value, None, user)
            continue
        try:
            rupees, number = _parse_fact(field, text, unit)
        except UnitError as e:
            errors[(period, field)] = str(e)
            continue
        if FIELD_BY_KEY[field].page_ref and not page:
            errors[(period, field)] = "Enter the page this figure was taken from."
            continue
        fact_unit = unit if rupees is not None else FIELD_BY_KEY[field].kind
        new_value = rupees if rupees is not None else _stored(
            {"value_rupees": None, "value_number": number, "field": field})
        if old is not None and old_value == new_value and old["page_ref"] == page:
            continue
        db.execute(
            "INSERT INTO facts (analysis_id, period, field, value_rupees, value_number, unit, "
            "entered_text, page_ref, source, saved_by, saved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'entered', ?, ?) "
            "ON CONFLICT (analysis_id, period, field) DO UPDATE SET "
            "value_rupees = excluded.value_rupees, value_number = excluded.value_number, "
            "unit = excluded.unit, entered_text = excluded.entered_text, "
            "page_ref = excluded.page_ref, saved_by = excluded.saved_by, "
            "saved_at = excluded.saved_at",
            (analysis_id, period, field, rupees, number, fact_unit, text, page, user, now),
        )
        _audit_fact(db, a, period, field, old_value, new_value, user)
    _touch(analysis_id)
    db.commit()
    return errors


def _json_value(v):
    return v if v is None or isinstance(v, int) else str(v)


def _audit_fact(db, a: dict, period: str, field: str, old, new, user: str) -> None:
    log_event(db, "fact_changed", user, company_id=a["company_id"], details={
        "analysis_id": a["id"], "period": period, "field": field,
        "previous": _json_value(old), "new": _json_value(new),
    })


def fact_history(analysis_id: str, period: str, field: str) -> list[dict]:
    """Every audited change to one figure, oldest first."""
    rows = get_db().execute(
        "SELECT user_id, timestamp, details FROM audit_log "
        "WHERE event_type = 'fact_changed' AND details LIKE ? ORDER BY id",
        (f'%"analysis_id": "{analysis_id}"%',),
    ).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["details"])
        if d.get("period") == period and d.get("field") == field:
            out.append({"previous": d.get("previous"), "new": d.get("new"),
                        "by": r["user_id"], "at": r["timestamp"]})
    return out


# ── Assumptions ──────────────────────────────────────────────────────────────

def load_assumptions(analysis_id: str) -> dict:
    """{key: {"value": Fraction, "text", "source", "as_of", "saved_by", "saved_at"}}"""
    out = {}
    for r in get_db().execute("SELECT * FROM assumptions WHERE analysis_id = ?", (analysis_id,)):
        if r["name"] in ASSUMPTION_BY_KEY:
            out[r["name"]] = {"value": parse_assumption(r["name"], r["value"]), "text": r["value"],
                              "source": r["source"], "as_of": r["as_of"],
                              "saved_by": r["saved_by"], "saved_at": r["saved_at"]}
    return out


def assumption_values(analysis_id: str) -> dict:
    return {k: v["value"] for k, v in load_assumptions(analysis_id).items()}


def save_assumptions(analysis_id: str, entries: dict, user: str) -> dict:
    """
    entries: {key: (value text, source, as_of)}. An empty value deletes the assumption.
    A value needs a source and a date (YYYY-MM-DD, not in the future). Returns
    {key: error} for assumptions not saved.
    """
    a = get_analysis(analysis_id)
    if not a:
        raise ValueError("Unknown analysis.")
    db = get_db()
    current = load_assumptions(analysis_id)
    errors, now = {}, _now()
    for key, (text, source, as_of) in entries.items():
        if key not in ASSUMPTION_BY_KEY:
            continue
        text, source, as_of = (text or "").strip(), (source or "").strip(), (as_of or "").strip()
        old = current.get(key)
        if not text:
            if old:
                db.execute("DELETE FROM assumptions WHERE analysis_id = ? AND name = ?",
                           (analysis_id, key))
                _audit_assumption(db, a, key, old, None, user)
            continue
        try:
            parse_assumption(key, text)
            if not source:
                raise ValueError("Enter the source of this value.")
            if date.fromisoformat(as_of) > date.today():
                raise ValueError("The date cannot be in the future.")
        except ValueError as e:
            msg = str(e)
            if "isoformat" in msg or "Invalid isoformat" in msg:
                msg = "Enter the date as YYYY-MM-DD."
            errors[key] = msg
            continue
        new = {"text": text, "source": source[:200], "as_of": as_of}
        if old and all(old[k] == new[k] for k in new):
            continue
        db.execute(
            "INSERT INTO assumptions (analysis_id, name, value, source, as_of, saved_by, saved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (analysis_id, name) DO UPDATE SET "
            "value = excluded.value, source = excluded.source, as_of = excluded.as_of, "
            "saved_by = excluded.saved_by, saved_at = excluded.saved_at",
            (analysis_id, key, text, new["source"], as_of, user, now),
        )
        _audit_assumption(db, a, key, old, new, user)
    _touch(analysis_id)
    db.commit()
    return errors


def _audit_assumption(db, a: dict, key: str, old, new, user: str) -> None:
    def view(x):
        return None if x is None else {"value": x["text"], "source": x["source"], "as_of": x["as_of"]}
    log_event(db, "assumption_changed", user, company_id=a["company_id"], details={
        "analysis_id": a["id"], "name": key, "previous": view(old), "new": view(new),
    })
