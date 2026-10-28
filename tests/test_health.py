"""/healthz is public and minimal; /health needs the owner's login and shows everything."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client():
    from app import create_app
    return TestClient(create_app(), base_url="https://testserver")


def _login(client, owner):
    from security.auth import create_session
    client.cookies.set("shafin_session", create_session(user_id="admin"))


def test_healthz_is_public_and_says_only_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_healthz_reveals_nothing_when_the_database_is_down(client, monkeypatch):
    import database.connection as conn
    monkeypatch.setattr(conn, "_connection", None)
    r = client.get("/healthz")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}


def test_health_needs_login(client):
    r = client.get("/health", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"
    assert client.get("/health", headers={"accept": "application/json"}).status_code == 401


def test_health_shows_full_status_when_logged_in(client, owner):
    _login(client, owner)
    r = client.get("/health")
    assert r.status_code == 200
    for text in ("Post-quantum", "ML-KEM-768", "ML-DSA-65", "Security self-test", "Passed",
                 "Audit chain", "Signing key", "Last backup"):
        assert text in r.text, text


def test_docker_health_checks_use_healthz():
    for name in ("Dockerfile", "docker-compose.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "/healthz" in text, name
