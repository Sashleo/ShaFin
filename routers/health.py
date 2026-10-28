"""routers/health.py — Owner health dashboard (login-protected).

Shows the full status: database, post-quantum library and algorithms, security
self-test, signing key, audit chain, last backup and the optional secondary backup
directory. The public /healthz probe (app.py) says only "ok" or "unavailable".
"""

from __future__ import annotations

import os

import structlog
from fastapi import APIRouter, Request
from database.connection import get_db
from routers.common import templates
from security.auth import require_session

log       = structlog.get_logger()
router    = APIRouter()


@router.get("")
async def health_page(request: Request):
    require_session(request)

    db = get_db()

    db_open = False
    try:
        db.execute("SELECT 1")
        db_open = True
    except Exception:
        pass

    signing_key   = False
    signing_algo  = None
    try:
        row = db.execute(
            "SELECT algorithm FROM pqc_keys WHERE key_type='signing' AND is_active=1 LIMIT 1"
        ).fetchone()
        signing_key  = bool(row)
        signing_algo = row["algorithm"] if row else None
    except Exception:
        pass

    audit = {"valid": False, "total": 0, "checked": 0, "reason": "not checked"}
    try:
        from security.audit import verify_chain_detailed
        audit = verify_chain_detailed(db)
    except Exception as e:
        audit["reason"] = str(e)[:120]

    backup = None
    try:
        from database.backup import latest_backup
        backup = latest_backup()
    except Exception:
        pass

    from security.pqc import KEM_ALGORITHM, SIG_ALGORITHM, require_pqc
    from security.selftest import run_self_test
    pqc = {"kem": KEM_ALGORITHM, "sig": SIG_ALGORITHM}
    try:
        pqc["liboqs_version"] = require_pqc()
    except Exception as e:
        pqc["error"] = str(e)[:200]
    self_test_failures = run_self_test()

    from config.settings import settings as _settings
    backup_copy_dir = _settings.BACKUP_COPY_DIR or ""
    backup_copy_dir_ok = os.path.isdir(backup_copy_dir) if backup_copy_dir else None

    return templates.TemplateResponse(request, "health.html", {
        "active_page":        "health",
        "version":            _settings.APP_VERSION,
        "pqc":                pqc,
        "self_test_failures": self_test_failures,
        "db_open":            db_open,
        "signing_key":        signing_key,
        "signing_algo":       signing_algo,
        "audit":              audit,
        "backup":             backup,
        "backup_copy_dir":    backup_copy_dir,
        "backup_copy_dir_ok": backup_copy_dir_ok,
    })
