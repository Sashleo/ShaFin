"""
reports/builder.py — Generate, store and read analysis reports.

A report is rendered to PDF and Word from one report model, each file is signed with
ML-DSA-65 and encrypted with the company's AES-256-GCM key, and the signatures are
stored beside the encrypted files. Downloads decrypt in memory and verify the
signature before serving (routers/reports.py).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from config.settings import settings
from database.connection import get_db
from reports.content import build_report_model
from reports.docx_renderer import render_docx
from reports.pdf_renderer import render_pdf
from reports.signer import ensure_signing_key, sign_report
from security.audit import log_event
from security.crypto import decrypt_bytes, encrypt_bytes
from security.keys import get_company_key, get_master_key

log = structlog.get_logger()


class ReportError(RuntimeError):
    pass


def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def generate_report(analysis: dict, company: dict, result, facts: dict, assumptions: dict,
                    charts: list, user: str) -> str:
    """Render, sign, encrypt and store a report. Returns the report id."""
    master_key = get_master_key()
    signing = ensure_signing_key(master_key)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    model = build_report_model(analysis, company, result, facts, assumptions, charts, signing)

    pdf = render_pdf(model, generated_at)
    docx = render_docx(model, generated_at)
    pdf_sig, err = sign_report(pdf, master_key)
    if err:
        raise ReportError(f"Signing failed: {err}")
    docx_sig, err = sign_report(docx, master_key)
    if err:
        raise ReportError(f"Signing failed: {err}")

    rid = uuid.uuid4().hex
    os.makedirs(settings.REPORTS_DIR, exist_ok=True)
    base = os.path.join(settings.REPORTS_DIR, rid)
    key = get_company_key(company["id"])
    paths = {"pdf": base + ".pdf.enc", "docx": base + ".docx.enc",
             "pdf_sig": base + ".pdf.sig", "docx_sig": base + ".docx.sig"}
    _write(paths["pdf"], encrypt_bytes(pdf, key))
    _write(paths["docx"], encrypt_bytes(docx, key))
    _write(paths["pdf_sig"], pdf_sig)
    _write(paths["docx_sig"], docx_sig)

    db = get_db()
    db.execute(
        "INSERT INTO reports (id, company_id, analysis_id, title, pdf_path, docx_path, "
        "pdf_signature_path, docx_signature_path, signing_algo, signing_fingerprint, created_by, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, company["id"], analysis["id"], model["title"], paths["pdf"], paths["docx"],
         paths["pdf_sig"], paths["docx_sig"], signing["algorithm"], signing["fingerprint"], user,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    db.commit()
    log_event(db, "report_generated", user, company_id=company["id"],
              details={"report_id": rid, "analysis_id": analysis["id"],
                       "fingerprint": signing["fingerprint"]})
    log.info("Report generated", report_id=rid, pdf_kb=len(pdf) // 1024)
    return rid


def list_reports() -> list[dict]:
    rows = get_db().execute(
        "SELECT r.*, c.name AS company_name, a.name AS analysis_name FROM reports r "
        "JOIN companies c ON c.id = r.company_id JOIN analyses a ON a.id = r.analysis_id "
        "ORDER BY r.created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_report(report_id: str) -> Optional[dict]:
    row = get_db().execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def read_report_file(file_path: str, key: bytes) -> Optional[bytes]:
    """Decrypt a stored report in memory. None if missing or if decryption fails."""
    if not file_path or not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        return decrypt_bytes(f.read(), key)
