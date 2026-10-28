"""
routers/settings.py — Security status, the threshold table, the audit chain, the
owner's password and two-factor authentication.

Settings keeps no rates. Rates are assumptions entered per analysis.
"""

from html import escape

import pyotp
import structlog
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from config.settings import settings
from database.connection import get_db
from database.thresholds import delete_threshold, list_thresholds, metric_catalogue, save_threshold
from intelligence.fields import COMPANY_TYPES
from reports.signer import get_public_key_info
from routers.common import templates, user_of
from security.audit import log_event, verify_chain_detailed
from security.auth import generate_totp_qr_base64, generate_totp_secret, require_session
from security.crypto import hash_password, verify_password
from security.pqc import KEM_ALGORITHM, SIG_ALGORITHM

log    = structlog.get_logger()
router = APIRouter()


def _alert(kind: str, text: str) -> HTMLResponse:
    return HTMLResponse(f'<div class="alert alert--{kind}" role="status">{escape(text)}</div>')


def _user_row(request: Request):
    return get_db().execute("SELECT * FROM users WHERE username = ?",
                            (user_of(request),)).fetchone()


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request):
    require_session(request)
    user = _user_row(request)
    thresholds = {t: [] for t in COMPANY_TYPES}
    for row in list_thresholds():
        thresholds[row["company_type"]].append(row)
    return templates.TemplateResponse(request, "settings.html", {
        "active_page": "settings",
        "kem": KEM_ALGORITHM,
        "sig": SIG_ALGORITHM,
        "signing_key": get_public_key_info(),
        "totp_enabled": bool(user and user["totp_enabled"]),
        "thresholds": thresholds,
        "catalogue": {t: metric_catalogue(t) for t in COMPANY_TYPES},
        "threshold_error": request.query_params.get("threshold_error"),
        "r": verify_chain_detailed(get_db()),
        "version": settings.APP_VERSION,
        "db_path": settings.DATABASE_PATH,
    })


# ── Thresholds ───────────────────────────────────────────────────────────────

@router.post("/thresholds")
async def thresholds_save(request: Request, company_type: str = Form(...), metric: str = Form(...),
                          op: str = Form(...), value: str = Form(...), rationale: str = Form("")):
    require_session(request)
    try:
        save_threshold(company_type, metric, op, value, rationale, user_of(request))
    except ValueError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/settings?threshold_error={quote(str(e))}#thresholds",
                                status_code=303)
    return RedirectResponse("/settings#thresholds", status_code=303)


@router.post("/thresholds/{threshold_id}/delete")
async def thresholds_delete(request: Request, threshold_id: int):
    require_session(request)
    delete_threshold(threshold_id, user_of(request))
    return RedirectResponse("/settings#thresholds", status_code=303)


# ── Audit chain ──────────────────────────────────────────────────────────────

@router.post("/verify-audit", response_class=HTMLResponse)
async def verify_audit(request: Request):
    require_session(request)
    return templates.TemplateResponse(request, "partials/audit_report.html",
                                      {"r": verify_chain_detailed(get_db())})


# ── Password ─────────────────────────────────────────────────────────────────

@router.post("/change-password", response_class=HTMLResponse)
async def change_password(request: Request, current_password: str = Form(...),
                          new_password: str = Form(...), confirm_password: str = Form(...)):
    require_session(request)
    if new_password != confirm_password:
        return _alert("neg", "New passwords do not match.")
    from routers.auth import _password_policy_error
    policy = _password_policy_error(new_password)
    if policy:
        return _alert("neg", policy)
    user = _user_row(request)
    if not user or not verify_password(current_password, user["password_hash"]):
        return _alert("neg", "Current password is incorrect.")
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (hash_password(new_password), user["id"]))
    db.commit()
    log_event(db, "password_changed", user_of(request))
    return _alert("pos", "Password updated.")


# ── Two-factor authentication ────────────────────────────────────────────────

@router.post("/setup-totp", response_class=HTMLResponse)
async def setup_totp(request: Request):
    require_session(request)
    user = _user_row(request)
    if not user:
        return _alert("neg", "Session error. Please log in again.")
    secret = generate_totp_secret()
    db = get_db()
    db.execute("UPDATE users SET totp_secret_pending = ? WHERE id = ?", (secret, user["id"]))
    db.commit()
    qr = generate_totp_qr_base64(secret)
    return HTMLResponse(f"""
    <div style="margin-top:16px">
      <p class="form-help">Scan this code with your authenticator app, then enter the 6-digit code.
        Or type the key: <code>{escape(secret)}</code></p>
      <img src="data:image/png;base64,{qr}" alt="Two-factor setup QR code" width="180" height="180">
      <form hx-post="/settings/confirm-totp" hx-target="#totp-result" hx-swap="innerHTML" class="form-row">
        <div class="form-group">
          <label class="form-label" for="totp-confirm">Code</label>
          <input id="totp-confirm" class="form-input" name="totp_code" maxlength="6" pattern="[0-9]{{6}}"
                 inputmode="numeric" autocomplete="one-time-code" required>
        </div>
        <button type="submit" class="btn btn-primary">Turn on 2FA</button>
      </form>
      <div id="totp-result"></div>
    </div>""")


@router.post("/confirm-totp", response_class=HTMLResponse)
async def confirm_totp(request: Request, totp_code: str = Form(...)):
    require_session(request)
    user = _user_row(request)
    if not user or not user["totp_secret_pending"]:
        return _alert("neg", "No two-factor setup is pending.")
    if not pyotp.TOTP(user["totp_secret_pending"]).verify(totp_code, valid_window=1):
        return _alert("neg", "That code is not valid. Try again.")
    db = get_db()
    db.execute("UPDATE users SET totp_secret = totp_secret_pending, totp_secret_pending = NULL, "
               "totp_enabled = 1 WHERE id = ?", (user["id"],))
    db.commit()
    log_event(db, "totp_enabled", user_of(request))
    return _alert("pos", "Two-factor authentication is on. It is needed at every login.")


@router.post("/disable-totp", response_class=HTMLResponse)
async def disable_totp(request: Request, totp_code: str = Form(...)):
    require_session(request)
    user = _user_row(request)
    if not user or not user["totp_secret"]:
        return _alert("neg", "Two-factor authentication is not on.")
    if not pyotp.TOTP(user["totp_secret"]).verify(totp_code, valid_window=1):
        return _alert("neg", "That code is not valid.")
    db = get_db()
    db.execute("UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = ?", (user["id"],))
    db.commit()
    log_event(db, "totp_disabled", user_of(request))
    return _alert("pos", "Two-factor authentication is off. The Data page needs it.")
