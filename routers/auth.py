"""
routers/auth.py — Login, logout, and first-run setup routes.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse

import structlog

from security.auth import (
    verify_totp, create_session, invalidate_session,
    check_lockout, record_failed_attempt, clear_attempts,
)
from security.crypto import hash_password, verify_password
from database.connection import get_db
from config.settings import settings
from security.audit import log_event
from routers.common import templates

log      = structlog.get_logger()
router   = APIRouter()


_COMMON_PASSWORDS = {
    "password", "password123", "12345678", "123456789", "1234567890",
    "qwerty", "qwertyuiop", "admin", "administrator", "letmein",
    "welcome", "changeme", "iloveyou", "shafin", "shafin123",
    "abc123456", "passw0rd", "adminadmin", "root", "toor",
}


def _password_policy_error(password: str) -> Optional[str]:
    """Return an error string if the password fails policy, else None."""
    if len(password) < 12:
        return "Admin password must be at least 12 characters."
    if password.lower() in _COMMON_PASSWORDS:
        return "That password is too common - choose a stronger one."
    if password.isdigit() or password.isalpha():
        return "Password must mix letters, digits and/or symbols."
    return None


def _get_or_create_admin(db) -> Optional[dict]:
    """Get admin user, or return None if none exists yet."""
    row = db.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
    return dict(row) if row else None


def _create_admin(db, password: str) -> dict:
    """Create the initial admin user."""
    user_id   = str(uuid.uuid4())
    pwd_hash  = hash_password(password)
    import secrets as s
    master_salt = s.token_bytes(32)
    now = datetime.utcnow().isoformat()

    db.execute(
        """
        INSERT INTO users (id, username, password_hash, totp_secret, totp_enabled,
                           master_salt, created_at)
        VALUES (?, 'admin', ?, NULL, 0, ?, ?)
        """,
        (user_id, pwd_hash, master_salt, now),
    )
    db.commit()
    return _get_or_create_admin(db)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, redirect to dashboard
    token   = request.cookies.get("shafin_session")
    from security.auth import get_session
    session = get_session(token) if token else None
    if session:
        return RedirectResponse(url="/dashboard", status_code=302)

    db    = get_db()
    admin = _get_or_create_admin(db)

    if not admin:
        # First-run: show setup page
        return templates.TemplateResponse(request, "login.html", {
            "version":  settings.APP_VERSION,
            "first_run": True,
        })

    return templates.TemplateResponse(request, "login.html", {
        "version": settings.APP_VERSION,
    })


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    totp_code: Optional[str] = Form(None),
    bootstrap_token: Optional[str] = Form(None),
):
    ip = request.client.host if request.client else "unknown"

    # Check lockout
    lockout = check_lockout(ip)
    if lockout:
        return templates.TemplateResponse(request, "login.html", {
            "version":         settings.APP_VERSION,
            "lockout_seconds": lockout,
        })

    db    = get_db()
    admin = _get_or_create_admin(db)

    # First run: create the owner account (gated to local requests or the token; password policy)
    if not admin:
        # Gate: request must come from localhost / private network, OR a matching token.
        _priv = ip in ("127.0.0.1", "::1", "localhost")
        _priv = _priv or ip.startswith("172.") or ip.startswith("192.168.") or ip.startswith("10.")
        is_local = _priv
        token_ok = bool(settings.ADMIN_BOOTSTRAP_TOKEN) and \
            bootstrap_token == settings.ADMIN_BOOTSTRAP_TOKEN
        if not (is_local or token_ok):
            log.warning("Blocked first-run admin creation from non-local host", ip=ip)
            return templates.TemplateResponse(request, "login.html", {
                "version": settings.APP_VERSION,
                "error":   "First-run admin creation must originate from localhost or "
                           "supply a valid ADMIN_BOOTSTRAP_TOKEN.",
                "first_run": True,
            }, status_code=403)
        pw_err = _password_policy_error(password)
        if pw_err:
            return templates.TemplateResponse(request, "login.html", {
                "version": settings.APP_VERSION,
                "error":   pw_err,
                "first_run": True,
            })
        admin = _create_admin(db, password)
        from reports.signer import ensure_signing_key
        from security.keys import get_master_key
        ensure_signing_key(get_master_key())
        log.info("Admin account created on first run", ip=ip)

    # Verify credentials
    if username != "admin" or not verify_password(password, admin["password_hash"]):
        locked = record_failed_attempt(ip)
        log_event(db, "login_failed", username[:40], details={"locked": locked}, ip_address=ip)
        return templates.TemplateResponse(request, "login.html", {
            "version": settings.APP_VERSION,
            "error":   "Invalid username or password." + (" Account locked." if locked else ""),
        })

    # Verify TOTP if enabled
    if admin["totp_enabled"] and admin["totp_secret"]:
        if not totp_code:
            return templates.TemplateResponse(request, "login.html", {
                "version":       settings.APP_VERSION,
                "totp_required": True,
            })
        if not verify_totp(admin["totp_secret"], totp_code):
            record_failed_attempt(ip)
            log_event(db, "login_failed", "admin", details={"reason": "2FA code"}, ip_address=ip)
            return templates.TemplateResponse(request, "login.html", {
                "version":       settings.APP_VERSION,
                "error":         "Invalid 2FA code.",
                "totp_required": True,
            })

    clear_attempts(ip)

    # Update last_login
    db.execute(
        "UPDATE users SET last_login = ? WHERE username = 'admin'",
        (datetime.utcnow().isoformat(),),
    )
    db.commit()

    # Create session with device binding
    session_token = create_session(user_id="admin", request=request)

    log.info("Admin logged in", ip=ip)
    log_event(db, "login_success", "admin", ip_address=ip)

    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie(
        key="shafin_session",
        value=session_token,
        httponly=True,
        samesite="strict",
        secure=True,
        max_age=settings.SESSION_EXPIRE_HOURS * 3600,
    )
    return resp


# ── Logout ────────────────────────────────────────────────────────────────────

@router.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("shafin_session")
    if token:
        invalidate_session(token)
        log_event(get_db(), "logout", getattr(request.state, "user_id", "admin"))
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("shafin_session")
    return resp
