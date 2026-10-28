"""
conftest.py - Shared fixtures.

- Every test gets a fresh in-memory SQLite database with ShaFin's schema, installed as
  the app's connection. SQLite and SQLCipher share the SQL dialect; only the file
  encryption differs, and that is tested through the Docker image's startup.
- No network: any test that opens an internet socket fails.
- The cryptography is real: the tests run in the Docker image, which has liboqs.
"""
import os
import socket
import sqlite3

import pytest

# Throwaway values so config.settings validates; CI passes its own random ones.
os.environ.setdefault("APP_SECRET_KEY", "test-only-secret-key-0123456789abcdef0123456789")
os.environ.setdefault("DB_MASTER_PASSWORD", "test-only-db-password")

import database.connection as _db_conn  # noqa: E402
from database.schema import run_migrations  # noqa: E402


@pytest.fixture(autouse=True)
def db(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    monkeypatch.setattr(_db_conn, "_connection", conn)
    run_migrations()
    yield conn
    conn.close()


@pytest.fixture
def owner(db):
    """The owner account, as first-run login creates it."""
    from routers.auth import _create_admin
    return _create_admin(db, "correct horse battery 9")


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    attempts: list = []

    def _guard(real):
        def connect(self, address, *args):
            if self.family == getattr(socket, "AF_UNIX", None):
                return real(self, address, *args)
            attempts.append(address)
            raise OSError(f"network access is disabled in tests: {address}")
        return connect

    monkeypatch.setattr(socket.socket, "connect", _guard(_real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _guard(_real_connect_ex))
    yield
    if attempts:
        pytest.fail(f"test opened a network connection: {attempts}")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app(), base_url="https://testserver")


@pytest.fixture
def logged_in(client, owner):
    """A client with the owner's session cookie."""
    from security.auth import create_session
    client.cookies.set("shafin_session", create_session(user_id="admin"))
    return client


@pytest.fixture
def reports_dir(tmp_path, monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "REPORTS_DIR", str(tmp_path / "reports"))
    return tmp_path / "reports"
