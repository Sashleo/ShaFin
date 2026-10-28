"""
routers/reports.py — Report listing and downloads.

Every download:
1. decrypts the stored file in memory with the company's key;
2. verifies its ML-DSA-65 signature, and refuses with 409 if it does not match;
3. is recorded in the audit log.
The signature files and the public signing key can be downloaded, so anyone can
check a report with liboqs.
"""

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

import structlog

from database.connection import get_db
from reports.builder import get_report, list_reports, read_report_file
from reports.signer import get_public_key_info, verify_report
from routers.common import templates, user_of
from security.audit import log_event
from security.auth import require_session

log    = structlog.get_logger()
router = APIRouter()

_MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _get_company_key(company_id: str) -> bytes:
    from security.keys import get_company_key
    return get_company_key(company_id)


def _refusal(request: Request, title: str, detail: str) -> HTMLResponse:
    return templates.TemplateResponse(request, "report_refused.html",
                                      {"title": title, "detail": detail}, status_code=409)


def _filename(record: dict, kind: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9 _-]", "", record.get("title") or "report").strip()[:60] or "report"
    return f"{stem} {record['id'][:8]}.{kind}"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def reports_page(request: Request):
    require_session(request)
    return templates.TemplateResponse(request, "reports.html", {
        "active_page": "reports",
        "reports": list_reports(),
        "signing_key": get_public_key_info(),
    })


@router.get("/signing-key.pub")
async def signing_public_key(request: Request):
    require_session(request)
    info = get_public_key_info()
    if not info:
        raise HTTPException(404, "No signing key yet")
    return Response(content=bytes(info["public_key"]), media_type="application/octet-stream",
                    headers={"Content-Disposition":
                             f'attachment; filename="shafin-{info["fingerprint"]}.ml-dsa-65.pub"'})


async def _download(request: Request, report_id: str, kind: str):
    require_session(request)
    record = get_report(report_id)
    if not record:
        raise HTTPException(404, "Report not found")
    try:
        key = _get_company_key(record["company_id"])
    except Exception as e:
        log.error("Key derivation failed", error=str(e))
        raise HTTPException(500, "Could not derive the decryption key")

    data = read_report_file(record[f"{kind}_path"], key)
    if data is None:
        return _refusal(request, "The report file could not be decrypted",
                        "The file is missing, or it does not match this company's key. "
                        "Generate the report again from the Analyser.")
    try:
        with open(record[f"{kind}_signature_path"], "rb") as f:
            signature = f.read()
    except OSError:
        return _refusal(request, "The report's signature is missing",
                        "A report is only served with its signature. Generate it again.")
    valid, msg = verify_report(data, signature)
    if not valid:
        log.error("Report signature mismatch; refusing to serve", report_id=report_id, msg=msg)
        return _refusal(request, "The report's signature does not match",
                        "The file may have been changed after it was signed. "
                        "Generate the report again from the Analyser.")

    log_event(get_db(), "report_downloaded", user_of(request), company_id=record["company_id"],
              details={"report_id": report_id, "format": kind})
    return Response(content=data, media_type=_MEDIA[kind], headers={
        "Content-Disposition": f'attachment; filename="{_filename(record, kind)}"',
        "X-Report-Signature": "verified ML-DSA-65",
    })


@router.get("/{report_id}/pdf")
async def download_pdf(request: Request, report_id: str):
    return await _download(request, report_id, "pdf")


@router.get("/{report_id}/docx")
async def download_docx(request: Request, report_id: str):
    return await _download(request, report_id, "docx")


@router.get("/{report_id}/{kind}.sig")
async def download_signature(request: Request, report_id: str, kind: str):
    require_session(request)
    record = get_report(report_id)
    if not record or kind not in _MEDIA:
        raise HTTPException(404, "Signature not found")
    with open(record[f"{kind}_signature_path"], "rb") as f:
        sig = f.read()
    return Response(content=sig, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{_filename(record, kind)}.sig"'})
