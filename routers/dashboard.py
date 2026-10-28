"""
routers/dashboard.py — The start page: companies, recent analyses and reports.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from database.connection import get_db
from database.companies import list_companies
from routers.common import templates
from security.auth import require_session

router = APIRouter()


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    require_session(request)
    db = get_db()
    recent = db.execute(
        "SELECT a.id, a.name, a.current_label, a.prior_label, a.updated_at, c.name AS company_name, "
        "c.company_type FROM analyses a JOIN companies c ON c.id = a.company_id "
        "ORDER BY a.updated_at DESC LIMIT 8"
    ).fetchall()
    report_count = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    return templates.TemplateResponse(request, "dashboard.html", {
        "active_page": "dashboard",
        "companies": list_companies(),
        "recent": [dict(r) for r in recent],
        "report_count": report_count,
    })
