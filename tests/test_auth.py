"""Login, first-run owner creation, lockout, two-factor login, logout; all audited."""

import pyotp
import pytest

from config.settings import settings
from security import auth


BOOTSTRAP = "fictional-bootstrap-token"


@pytest.fixture
def bootstrap(monkeypatch):
    """The test client is not a local address, so first-run creation needs the token."""
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_TOKEN", BOOTSTRAP)


@pytest.fixture(autouse=True)
def _clear_lockouts():
    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()


def _events(db, kind):
    return db.execute("SELECT COUNT(*) FROM audit_log WHERE event_type = ?", (kind,)).fetchone()[0]


def test_first_run_from_a_remote_address_needs_the_bootstrap_token(client, db):
    r = client.post("/login", data={"username": "admin", "password": "Fictional-Owner-2026"})
    assert r.status_code == 403
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


@pytest.mark.usefixtures("bootstrap")
def test_first_run_creates_the_owner_and_signing_key(client, db):
    r = client.post("/login", data={"username": "admin", "password": "Fictional-Owner-2026",
                                    "bootstrap_token": BOOTSTRAP},
                    follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/dashboard"
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert db.execute("SELECT algorithm FROM pqc_keys WHERE is_active = 1").fetchone()[0] == "ML-DSA-65"
    assert _events(db, "login_success") == 1


@pytest.mark.usefixtures("bootstrap")
@pytest.mark.parametrize("password", ["short1!", "password123", "abcdefghijklmnop", "123456789012"])
def test_first_run_refuses_weak_passwords(client, db, password):
    r = client.post("/login", data={"username": "admin", "password": password,
                                    "bootstrap_token": BOOTSTRAP})
    assert r.status_code == 200
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_wrong_password_is_refused_and_audited(client, owner, db):
    r = client.post("/login", data={"username": "admin", "password": "wrong password 1"})
    assert "Invalid username or password" in r.text and "shafin_session" not in r.cookies
    assert _events(db, "login_failed") == 1


def test_lockout_after_repeated_failures(client, owner):
    for _ in range(settings.MAX_LOGIN_ATTEMPTS):
        client.post("/login", data={"username": "admin", "password": "wrong password 1"})
    r = client.post("/login", data={"username": "admin", "password": "correct horse battery 9"})
    assert "shafin_session" not in r.cookies


def test_two_factor_is_needed_at_login_when_on(client, owner, db):
    secret = pyotp.random_base32()
    db.execute("UPDATE users SET totp_secret = ?, totp_enabled = 1", (secret,))
    db.commit()
    r = client.post("/login", data={"username": "admin", "password": "correct horse battery 9"},
                    follow_redirects=False)
    assert r.status_code == 200 and "shafin_session" not in r.cookies
    r = client.post("/login", data={"username": "admin", "password": "correct horse battery 9",
                                    "totp_code": "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"},
                    follow_redirects=False)
    assert "Invalid 2FA code" in r.text
    r = client.post("/login", data={"username": "admin", "password": "correct horse battery 9",
                                    "totp_code": pyotp.TOTP(secret).now()}, follow_redirects=False)
    assert r.status_code == 302 and "shafin_session" in r.cookies


def test_logout_ends_the_session(logged_in, db):
    assert logged_in.get("/dashboard").status_code == 200
    logged_in.get("/logout", follow_redirects=False)
    assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert _events(db, "logout") == 1


@pytest.mark.usefixtures("bootstrap")
def test_session_cookie_flags(client, db):
    r = client.post("/login", data={"username": "admin", "password": "Fictional-Owner-2026",
                                    "bootstrap_token": BOOTSTRAP},
                    follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie


def test_session_payload_is_encrypted_at_rest(logged_in, db):
    row = db.execute("SELECT payload_enc FROM sessions").fetchone()
    assert b"admin" not in bytes(row["payload_enc"])


def test_a_stolen_cookie_from_another_device_is_refused(client, owner, db):
    from security.auth import get_session

    class _Req:
        class client:
            host = "10.0.0.1"
        headers = {"user-agent": "browser A"}

    token = auth.create_session("admin", request=_Req)
    _Req.headers = {"user-agent": "browser B"}
    assert get_session(token, request=_Req) is None
    assert _events(db, "session_hijack_attempt") == 1


def test_security_headers(client):
    r = client.get("/login")
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["strict-transport-security"].startswith("max-age=")
