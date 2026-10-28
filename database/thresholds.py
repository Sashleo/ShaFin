"""
database/thresholds.py - The owner's flag thresholds, per company type.

Settings shows every threshold with its rationale; each can be edited, added or
deleted, and every change is audited. These are flags, not rates: ShaFin keeps no
rates in Settings.
"""

from __future__ import annotations

from datetime import datetime, timezone

from database.connection import get_db
from intelligence.bank import compute_bank_ratios
from intelligence.fields import COMPANY_TYPES
from intelligence.flags import OPS
from intelligence.ratios import compute_ratios
from intelligence.units import UnitError, parse_number
from security.audit import log_event


def metric_catalogue(company_type: str) -> dict:
    """{metric key: (label, unit)} of the metrics a threshold can test for this type."""
    metrics = (compute_bank_ratios({}, {}) if company_type == "bank"
               else compute_ratios({}, {}))
    return {m.key: (m.label, m.unit) for m in metrics if m.unit != "pkr"}


def list_thresholds(company_type: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM thresholds", ()
    if company_type:
        sql, args = sql + " WHERE company_type = ?", (company_type,)
    rows = get_db().execute(sql + " ORDER BY company_type, metric", args).fetchall()
    return [dict(r) for r in rows]


def _validate(company_type: str, metric: str, op: str, value: str, rationale: str) -> None:
    if company_type not in COMPANY_TYPES:
        raise ValueError("Unknown company type.")
    if metric not in metric_catalogue(company_type):
        raise ValueError("That metric is not computed for this company type.")
    if op not in OPS:
        raise ValueError("Choose a comparison.")
    try:
        parse_number(value)
    except UnitError:
        raise ValueError("The threshold must be a number.")
    if not rationale.strip():
        raise ValueError("Give the rationale for this threshold.")


def save_threshold(company_type: str, metric: str, op: str, value: str, rationale: str,
                   user: str) -> None:
    """Add or replace the threshold for (company type, metric)."""
    value, rationale = value.strip(), rationale.strip()
    _validate(company_type, metric, op, value, rationale)
    db = get_db()
    old = db.execute("SELECT op, value, rationale FROM thresholds WHERE company_type = ? AND "
                     "metric = ?", (company_type, metric)).fetchone()
    db.execute(
        "INSERT INTO thresholds (company_type, metric, op, value, rationale, updated_by, "
        "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (company_type, metric) DO UPDATE "
        "SET op = excluded.op, value = excluded.value, rationale = excluded.rationale, "
        "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
        (company_type, metric, op, value, rationale[:400], user,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    db.commit()
    log_event(db, "threshold_changed", user, details={
        "company_type": company_type, "metric": metric,
        "previous": dict(old) if old else None,
        "new": {"op": op, "value": value, "rationale": rationale[:400]},
    })


def delete_threshold(threshold_id: int, user: str) -> None:
    db = get_db()
    old = db.execute("SELECT * FROM thresholds WHERE id = ?", (threshold_id,)).fetchone()
    if not old:
        return
    db.execute("DELETE FROM thresholds WHERE id = ?", (threshold_id,))
    db.commit()
    log_event(db, "threshold_changed", user, details={
        "company_type": old["company_type"], "metric": old["metric"],
        "previous": {"op": old["op"], "value": old["value"], "rationale": old["rationale"]},
        "new": None,
    })
