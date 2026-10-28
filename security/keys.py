"""
security/keys.py - The master key and per-company keys, derived on demand.

master key  = Argon2id(DB_MASTER_PASSWORD, users.master_salt)
company key = derive_company_key(master key, the company's hybrid key material)
"""

from config.settings import settings
from database.connection import get_db
from security.crypto import CompanyKeyError, derive_company_key, derive_master_key


def get_master_key() -> bytes:
    row = get_db().execute("SELECT master_salt FROM users LIMIT 1").fetchone()
    if not row or not row["master_salt"]:
        raise CompanyKeyError("no master salt: create the owner account first")
    return derive_master_key(settings.DB_MASTER_PASSWORD, bytes(row["master_salt"]))


def get_company_key(company_id: str) -> bytes:
    row = get_db().execute(
        "SELECT id, salt, kem_private_key_enc, kem_ciphertext FROM companies WHERE id = ?",
        (company_id,),
    ).fetchone()
    if not row:
        raise CompanyKeyError(f"company {company_id} not found")
    return derive_company_key(get_master_key(), dict(row))
