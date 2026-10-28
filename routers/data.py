"""
routers/data.py — The Data page: every table in the database, read-only.

- Owner only, and only with two-factor authentication turned on.
- The table name must be a table listed in sqlite_master; it is never taken from
  the request as SQL. Sort columns must be visible columns of that table.
- Each request runs one SELECT on the data (paged, filtered and sorted in SQL), after
  one lookup in sqlite_master that checks the name and lists the columns. Both run
  with PRAGMA query_only on, so the connection refuses any write while they run.
- Password hashes, TOTP secrets, session tokens, keys, salts and every *_encrypted or
  *_enc column are never selected; the page and the CSV show them as "hidden".
- Every view, filter and CSV export is written to the audit log.
"""

from __future__ import annotations

import csv
import io
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from database.analyses import fact_history
from database.connection import get_db
from intelligence.fields import FIELD_BY_KEY
from routers.common import templates, user_of
from security.audit import log_event
from security.auth import require_session

router = APIRouter()

PAGE_SIZE = 50
HIDDEN = "hidden"   # shown in place of a column that is never selected
_HIDDEN_PARTS = ("hash", "secret", "token", "salt", "password", "_enc", "kem_", "payload")


def is_hidden(column: str) -> bool:
    """True for columns the Data page never selects."""
    c = column.lower()
    # Key material: public_key, kem_public_key, private_key_encrypted. Not key_type.
    is_key = c == "key" or c.endswith("_key") or "_key_" in c
    return is_key or any(part in c for part in _HIDDEN_PARTS)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@contextmanager
def _query_only(db):
    db.execute("PRAGMA query_only = ON")
    try:
        yield
    finally:
        db.execute("PRAGMA query_only = OFF")


def readonly_select(sql: str, params: tuple = ()) -> list:
    """Run one SELECT with the connection in query-only mode. Anything else is refused."""
    stripped = sql.strip()
    if not stripped.upper().startswith("SELECT") or ";" in stripped:
        raise ValueError("The Data page runs single SELECT statements only.")
    db = get_db()
    with _query_only(db):
        return db.execute(stripped, params).fetchall()


def _require_owner_with_2fa(request: Request) -> str:
    require_session(request)
    user = user_of(request)
    row = get_db().execute("SELECT totp_enabled FROM users WHERE username = ?", (user,)).fetchone()
    if not row or not row["totp_enabled"]:
        raise HTTPException(403, "The Data page needs two-factor authentication. "
                                 "Turn it on in Settings, then log in again.")
    return user


def table_columns(table: str) -> list[str]:
    """Columns of a table that exists in sqlite_master; 404 for any other name."""
    rows = readonly_select(
        "SELECT p.name FROM sqlite_master m JOIN pragma_table_info(m.name) p "
        "WHERE m.type = 'table' AND m.name = ? AND m.name NOT LIKE 'sqlite_%' ORDER BY p.cid",
        (table,),
    )
    if not rows:
        raise HTTPException(404, "No such table")
    return [r[0] for r in rows]


def _view_query(table: str, columns: list[str], q: str, sort: str, direction: str,
                page: int | None) -> tuple[str, tuple]:
    visible = [c for c in columns if not is_hidden(c)]
    select = ", ".join(_quote(c) for c in visible)
    sql = f"SELECT {select}, COUNT(*) OVER () AS _total FROM {_quote(table)}"
    params: list = []
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " WHERE " + " OR ".join(f"CAST({_quote(c)} AS TEXT) LIKE ? ESCAPE '\\'"
                                       for c in visible)
        params += [like] * len(visible)
    order = sort if sort in visible else visible[0]
    sql += f" ORDER BY {_quote(order)} {'DESC' if direction == 'desc' else 'ASC'}"
    if page is not None:
        sql += f" LIMIT {PAGE_SIZE} OFFSET {max(page - 1, 0) * PAGE_SIZE}"
    return sql, tuple(params)


def _audit(request: Request, view: str, **details) -> None:
    log_event(get_db(), "data_page_viewed", user_of(request), details={"view": view, **details},
              ip_address=request.client.host if request.client else None)


@router.get("", response_class=HTMLResponse)
async def data_index(request: Request):
    _require_owner_with_2fa(request)
    names = [r[0] for r in readonly_select(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]
    counts = {}
    if names:
        union = " UNION ALL ".join(f"SELECT ?, COUNT(*) FROM {_quote(n)}" for n in names)
        counts = dict(readonly_select(union, tuple(names)))
    _audit(request, "index")
    return templates.TemplateResponse(request, "data/index.html", {
        "active_page": "data", "tables": [(n, counts.get(n, 0)) for n in names],
    })


@router.get("/facts/{fact_id}/lineage", response_class=HTMLResponse)
async def fact_lineage(request: Request, fact_id: int):
    _require_owner_with_2fa(request)
    rows = readonly_select(
        "SELECT f.id, f.period, f.field, f.value_rupees, f.value_number, f.unit, f.entered_text, "
        "f.page_ref, f.source, f.saved_by, f.saved_at, a.id AS analysis_id, a.name AS analysis_name, "
        "a.current_label, a.prior_label, c.name AS company_name "
        "FROM facts f JOIN analyses a ON a.id = f.analysis_id JOIN companies c ON c.id = a.company_id "
        "WHERE f.id = ?", (fact_id,))
    if not rows:
        raise HTTPException(404, "No such figure")
    fact = dict(rows[0])
    field = FIELD_BY_KEY.get(fact["field"])
    _audit(request, "lineage", fact_id=fact_id)
    return templates.TemplateResponse(request, "data/lineage.html", {
        "active_page": "data", "fact": fact, "label": field.label if field else fact["field"],
        "history": fact_history(fact["analysis_id"], fact["period"], fact["field"]),
    })


@router.get("/{table}.csv")
async def data_csv(request: Request, table: str, q: str = "", sort: str = "", dir: str = "asc"):
    _require_owner_with_2fa(request)
    columns = table_columns(table)
    sql, params = _view_query(table, columns, q.strip(), sort, dir, page=None)
    rows = readonly_select(sql, params)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for r in rows:
        # A leading = + - @ would make a spreadsheet run the cell as a formula.
        writer.writerow([HIDDEN if is_hidden(c) else _csv_cell(r[c]) for c in columns])
    _audit(request, "csv", table=table, q=q, sort=sort, dir=dir, rows=len(rows))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(content=buf.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="shafin-{table}-{stamp}.csv"'})


@router.get("/{table}", response_class=HTMLResponse)
async def data_table(request: Request, table: str, q: str = "", sort: str = "", dir: str = "asc",
                     page: int = 1):
    _require_owner_with_2fa(request)
    columns = table_columns(table)
    sql, params = _view_query(table, columns, q.strip(), sort, dir, page=max(page, 1))
    rows = readonly_select(sql, params)
    visible = [c for c in columns if not is_hidden(c)]
    total = rows[0]["_total"] if rows else 0
    _audit(request, "table", table=table, q=q, sort=sort, dir=dir, page=page)
    return templates.TemplateResponse(request, "data/table.html", {
        "active_page": "data", "table": table, "columns": columns, "visible": visible,
        "hidden": [c for c in columns if is_hidden(c)],
        "rows": [[HIDDEN if is_hidden(c) else _cell(r[c]) for c in columns] for r in rows],
        "ids": [r["id"] if "id" in visible else None for r in rows],
        "q": q, "sort": sort if sort in visible else visible[0], "dir": dir,
        "page": max(page, 1), "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1), "total": total,
    })


def _csv_cell(value):
    if isinstance(value, str) and value[:1] in "=+-@":
        return "'" + value
    return value


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    if isinstance(value, str) and value.startswith("{"):
        try:
            return json.dumps(json.loads(value), ensure_ascii=False)
        except ValueError:
            return value
    return str(value)
