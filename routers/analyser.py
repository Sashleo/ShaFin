"""
routers/analyser.py - The Analyser: companies, analyses, the entry form, the
assumptions panel and the results.

/analyser                       companies, and a form to add one
/analyser/c/{company_id}        a company: its type, its analyses, a form for a new one
/analyser/a/{analysis_id}       an analysis: entry form, assumptions, results
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from database import analyses as store
from database.companies import (
    change_company_type, create_company, delete_company, get_company, list_companies,
    update_company,
)
from database.thresholds import list_thresholds
from intelligence.analyser import analyse
from intelligence.assumptions import assumptions_for
from intelligence.charts import bridge_chart, margins_chart
from intelligence.fields import PERIODS, grouped_fields
from intelligence.units import UNITS
from routers.common import templates, user_of
from security.auth import require_session

router = APIRouter()


def _with_error(url: str, error) -> RedirectResponse:
    return RedirectResponse(f"{url}?error={quote(str(error))}", status_code=303)


def _company_or_404(company_id: str) -> dict:
    company = get_company(company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    return company


def _analysis_or_404(analysis_id: str) -> tuple[dict, dict]:
    analysis = store.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return analysis, _company_or_404(analysis["company_id"])


def run_analysis(analysis: dict, company: dict):
    """Everything the analysis page and the reports show, computed from what is saved."""
    return analyse(
        company["company_type"],
        store.load_facts(analysis["id"]),
        store.assumption_values(analysis["id"]),
        list_thresholds(company["company_type"]),
        tolerance=UNITS[analysis["unit"]][1],
    )


def charts_for(analysis: dict, result) -> list[dict]:
    prior = store.load_facts(analysis["id"])["prior"]
    return [c for c in (bridge_chart(result.bridge), margins_chart(result, prior, analysis)) if c]


# ── Companies ────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def companies_page(request: Request):
    require_session(request)
    return templates.TemplateResponse(request, "analyser/companies.html", {
        "active_page": "analyser", "companies": list_companies(),
        "error": request.query_params.get("error"),
    })


@router.post("/companies")
async def companies_create(request: Request):
    require_session(request)
    form = await request.form()
    try:
        company = create_company(form.get("name", ""), form.get("company_type", ""),
                                 form.get("industry"), user_of(request))
    except ValueError as e:
        return _with_error("/analyser", e)
    return RedirectResponse(f"/analyser/c/{company['id']}", status_code=303)


@router.get("/c/{company_id}", response_class=HTMLResponse)
async def company_page(request: Request, company_id: str):
    require_session(request)
    company = _company_or_404(company_id)
    return templates.TemplateResponse(request, "analyser/company.html", {
        "active_page": "analyser", "company": company,
        "analyses": store.list_analyses(company_id),
        "error": request.query_params.get("error"),
    })


@router.post("/c/{company_id}/edit")
async def company_edit(request: Request, company_id: str):
    require_session(request)
    _company_or_404(company_id)
    form = await request.form()
    try:
        update_company(company_id, form.get("name", ""), form.get("industry"), user_of(request))
        change_company_type(company_id, form.get("company_type", ""), user_of(request))
    except ValueError as e:
        return _with_error(f"/analyser/c/{company_id}", e)
    return RedirectResponse(f"/analyser/c/{company_id}", status_code=303)


@router.post("/c/{company_id}/delete")
async def company_delete(request: Request, company_id: str):
    require_session(request)
    company = _company_or_404(company_id)
    form = await request.form()
    if form.get("confirm_name", "").strip() != company["name"]:
        return _with_error(f"/analyser/c/{company_id}", "Type the company name exactly to delete it.")
    delete_company(company_id, user_of(request))
    return RedirectResponse("/analyser", status_code=303)


@router.post("/c/{company_id}/analyses")
async def analysis_create(request: Request, company_id: str):
    require_session(request)
    _company_or_404(company_id)
    form = await request.form()
    try:
        aid = store.create_analysis(company_id, form.get("name", ""), form.get("current_label", ""),
                                    form.get("prior_label", ""), form.get("unit", ""),
                                    user_of(request))
    except ValueError as e:
        return _with_error(f"/analyser/c/{company_id}", e)
    return RedirectResponse(f"/analyser/a/{aid}", status_code=303)


# ── One analysis ─────────────────────────────────────────────────────────────

def _render_analysis(request: Request, analysis: dict, company: dict, *, fact_errors=None,
                     form_values=None, assumption_errors=None, assumption_form=None,
                     flash: str = "", status_code: int = 200):
    result = run_analysis(analysis, company)
    saved = store.load_assumptions(analysis["id"])
    return templates.TemplateResponse(request, "analyser/analysis.html", {
        "active_page": "analyser",
        "company": company,
        "analysis": analysis,
        "groups": grouped_fields(company["company_type"]),
        "periods": PERIODS,
        "values": form_values if form_values is not None
        else store.load_form_values(analysis["id"], analysis["unit"]),
        "fact_errors": fact_errors or {},
        "assumptions": assumptions_for(company["company_type"]),
        "saved_assumptions": saved,
        "assumption_form": assumption_form or {},
        "assumption_errors": assumption_errors or {},
        "result": result,
        "charts": charts_for(analysis, result),
        "flash": flash,
    }, status_code=status_code)


@router.get("/a/{analysis_id}", response_class=HTMLResponse)
async def analysis_page(request: Request, analysis_id: str):
    require_session(request)
    analysis, company = _analysis_or_404(analysis_id)
    flash = {"facts": "Figures saved.", "assumptions": "Assumptions saved.",
             "report": "Report generated, signed and encrypted; see Reports."
             }.get(request.query_params.get("saved", ""), "")
    return _render_analysis(request, analysis, company, flash=flash)


@router.post("/a/{analysis_id}/facts", response_class=HTMLResponse)
async def facts_save(request: Request, analysis_id: str):
    require_session(request)
    analysis, company = _analysis_or_404(analysis_id)
    form = await request.form()
    unit = form.get("unit", analysis["unit"])
    if unit not in UNITS:
        raise HTTPException(400, "Unknown unit")
    entries = {}
    for name, value in form.multi_items():
        period, sep, field = name.partition(":")
        if sep and period in PERIODS:
            entries[(period, field)] = value
    errors = store.save_facts(analysis_id, unit, entries, user_of(request))
    if unit != analysis["unit"]:
        store.set_unit(analysis_id, unit)
        analysis["unit"] = unit
    if errors:
        return _render_analysis(request, analysis, company, fact_errors=errors,
                                form_values=entries, status_code=422)
    return RedirectResponse(f"/analyser/a/{analysis_id}?saved=facts#figures", status_code=303)


@router.post("/a/{analysis_id}/assumptions", response_class=HTMLResponse)
async def assumptions_save(request: Request, analysis_id: str):
    require_session(request)
    analysis, company = _analysis_or_404(analysis_id)
    form = await request.form()
    entries = {a.key: (form.get(f"{a.key}:value", ""), form.get(f"{a.key}:source", ""),
                       form.get(f"{a.key}:as_of", ""))
               for a in assumptions_for(company["company_type"])}
    errors = store.save_assumptions(analysis_id, entries, user_of(request))
    if errors:
        return _render_analysis(request, analysis, company, assumption_errors=errors,
                                assumption_form=entries, status_code=422)
    return RedirectResponse(f"/analyser/a/{analysis_id}?saved=assumptions#assumptions",
                            status_code=303)


@router.post("/a/{analysis_id}/report")
async def report_generate(request: Request, analysis_id: str):
    require_session(request)
    analysis, company = _analysis_or_404(analysis_id)
    from reports.builder import generate_report
    result = run_analysis(analysis, company)
    generate_report(analysis, company, result, store.load_facts(analysis_id),
                    store.load_assumptions(analysis_id), charts_for(analysis, result),
                    user_of(request))
    return RedirectResponse(f"/analyser/a/{analysis_id}?saved=report", status_code=303)


@router.post("/a/{analysis_id}/delete")
async def analysis_delete(request: Request, analysis_id: str):
    require_session(request)
    analysis, company = _analysis_or_404(analysis_id)
    try:
        store.delete_analysis(analysis_id, user_of(request))
    except ValueError as e:
        return _with_error(f"/analyser/c/{company['id']}", e)
    return RedirectResponse(f"/analyser/c/{company['id']}", status_code=303)
