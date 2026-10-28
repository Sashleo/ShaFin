"""
database/companies.py - Companies: create, read, change type, delete.

Each company has its own salt and ML-KEM-768 + X25519 hybrid key material, from
which its report encryption key is derived. Deleting a company deletes its analyses,
figures, assumptions and reports, and destroys its key material, so its encrypted
report files can no longer be read.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from database.connection import get_db
from intelligence.fields import COMPANY_TYPES
from security.audit import log_event
from security.crypto import generate_salt, new_company_key_material
from security.keys import get_master_key

log = structlog.get_logger()

_PUBLIC_COLUMNS = "id, name, company_type, industry, created_at, updated_at"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_company(name: str, company_type: str, industry: Optional[str], user: str) -> dict:
    """Create a company. Raises if the hybrid key material cannot be made."""
    name = name.strip()
    if not name:
        raise ValueError("A company name is required.")
    if company_type not in COMPANY_TYPES:
        raise ValueError("Choose a company type.")
    km = new_company_key_material(get_master_key())
    cid, now = uuid.uuid4().hex, _now()
    db = get_db()
    db.execute(
        "INSERT INTO companies (id, name, company_type, industry, salt, kem_public_key, "
        "kem_private_key_enc, kem_ciphertext, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, name[:120], company_type, (industry or "").strip()[:80] or None, generate_salt(),
         km["kem_public_key"], km["kem_private_key_enc"], km["kem_ciphertext"], now, now),
    )
    db.commit()
    log_event(db, "company_created", user, company_id=cid,
              details={"name": name, "company_type": company_type})
    return get_company(cid)


def get_company(company_id: str) -> Optional[dict]:
    row = get_db().execute(
        f"SELECT {_PUBLIC_COLUMNS} FROM companies WHERE id = ?", (company_id,)
    ).fetchone()
    return dict(row) if row else None


def list_companies() -> list[dict]:
    rows = get_db().execute(
        f"SELECT {_PUBLIC_COLUMNS}, "
        "(SELECT COUNT(*) FROM analyses a WHERE a.company_id = companies.id) AS analysis_count "
        "FROM companies ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def update_company(company_id: str, name: str, industry: Optional[str], user: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("A company name is required.")
    db = get_db()
    db.execute("UPDATE companies SET name = ?, industry = ?, updated_at = ? WHERE id = ?",
               (name[:120], (industry or "").strip()[:80] or None, _now(), company_id))
    db.commit()
    log_event(db, "company_updated", user, company_id=company_id, details={"name": name})


def change_company_type(company_id: str, company_type: str, user: str) -> None:
    """Change the type. Entered figures are kept; fields that no longer apply are hidden."""
    if company_type not in COMPANY_TYPES:
        raise ValueError("Unknown company type.")
    company = get_company(company_id)
    if not company or company["company_type"] == company_type:
        return
    db = get_db()
    db.execute("UPDATE companies SET company_type = ?, updated_at = ? WHERE id = ?",
               (company_type, _now(), company_id))
    db.commit()
    log_event(db, "company_type_changed", user, company_id=company_id,
              details={"previous": company["company_type"], "new": company_type})


def delete_company(company_id: str, user: str) -> None:
    """Delete the company, everything entered for it and its report files."""
    db = get_db()
    company = get_company(company_id)
    if not company:
        return
    paths = []
    for r in db.execute("SELECT pdf_path, docx_path, pdf_signature_path, docx_signature_path "
                        "FROM reports WHERE company_id = ?", (company_id,)).fetchall():
        paths.extend(p for p in r if p)
    analyses = "SELECT id FROM analyses WHERE company_id = ?"
    try:
        db.execute(f"DELETE FROM facts WHERE analysis_id IN ({analyses})", (company_id,))
        db.execute(f"DELETE FROM assumptions WHERE analysis_id IN ({analyses})", (company_id,))
        db.execute("DELETE FROM reports WHERE company_id = ?", (company_id,))
        db.execute("DELETE FROM analyses WHERE company_id = ?", (company_id,))
        db.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    log_event(db, "company_deleted", user, company_id=company_id,
              details={"name": company["name"], "report_files_removed": len(paths)})
