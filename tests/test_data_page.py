"""
The Data page: owner with 2FA only, read-only, table names checked against
sqlite_master, sensitive columns hidden, lineage for each figure, every view audited.
"""

import sqlite3

import pytest

from routers.data import is_hidden, readonly_select


@pytest.fixture
def with_2fa(logged_in, db):
    db.execute("UPDATE users SET totp_enabled = 1, totp_secret = 'JBSWY3DPEHPK3PXP'")
    db.commit()
    return logged_in


def _views(db):
    return db.execute("SELECT COUNT(*) FROM audit_log WHERE event_type = 'data_page_viewed'").fetchone()[0]


# ── Access ───────────────────────────────────────────────────────────────────

def test_needs_login(client):
    assert client.get("/settings/data", headers={"accept": "application/json"}).status_code == 401


def test_needs_two_factor_authentication(logged_in):
    r = logged_in.get("/settings/data")
    assert r.status_code == 403 and "two-factor" in r.text


def test_lists_every_table_with_its_row_count(with_2fa):
    r = with_2fa.get("/settings/data")
    assert r.status_code == 200
    for table in ("users", "companies", "facts", "assumptions", "thresholds", "audit_log"):
        assert f'href="/settings/data/{table}"' in r.text


# ── Read-only ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "DELETE FROM users",
    "UPDATE users SET username = 'x'",
    "INSERT INTO thresholds (company_type) VALUES ('bank')",
    "DROP TABLE users",
    "SELECT 1; DELETE FROM users",
    "WITH x AS (SELECT 1) DELETE FROM users",
])
def test_anything_but_a_single_select_is_refused(sql):
    with pytest.raises(ValueError):
        readonly_select(sql)


def test_the_connection_refuses_writes_while_the_page_reads(db, owner):
    from routers.data import _query_only
    with _query_only(db):
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM users")
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    db.execute("UPDATE users SET last_login = 'x'")       # writable again afterwards


def test_viewing_changes_nothing_but_the_audit_log(with_2fa, db):
    before = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
              for t in ("users", "sessions", "companies", "thresholds")}
    with_2fa.get("/settings/data/users")
    with_2fa.get("/settings/data/thresholds?q=bank&sort=metric&dir=desc")
    after = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in before}
    assert before == after


# ── Table names ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["nope", "sqlite_sequence", "users%22%3B%20DROP%20TABLE%20users",
                                  "pragma_table_info"])
def test_unknown_table_names_are_404(with_2fa, name, db):
    assert with_2fa.get(f"/settings/data/{name}").status_code == 404
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_sort_by_a_hidden_or_unknown_column_falls_back_to_the_first_column(with_2fa):
    for sort in ("password_hash", 'id" DESC; --'):
        r = with_2fa.get("/settings/data/users", params={"sort": sort})
        assert r.status_code == 200
        assert "id ▲" in r.text


# ── Hidden columns ───────────────────────────────────────────────────────────

def test_sensitive_columns_are_hidden():
    for col in ("password_hash", "totp_secret", "totp_secret_pending", "master_salt", "token_hash",
                "payload_enc", "ip_ua_hash", "private_key_encrypted", "public_key", "salt",
                "kem_public_key", "kem_private_key_enc", "kem_ciphertext", "prev_hash",
                "entry_hash", "notes_encrypted"):
        assert is_hidden(col), col
    for col in ("id", "username", "name", "value_rupees", "entered_text", "source", "as_of",
                "saved_by", "company_type", "details", "key_type", "algorithm", "fingerprint"):
        assert not is_hidden(col), col


def test_secrets_never_reach_the_page_or_the_csv(with_2fa, db):
    secret = db.execute("SELECT password_hash, totp_secret FROM users").fetchone()
    for url in ("/settings/data/users", "/settings/data/users.csv", "/settings/data/sessions",
                "/settings/data/pqc_keys.csv"):
        body = with_2fa.get(url).text
        assert secret["password_hash"] not in body and "JBSWY3DPEHPK3PXP" not in body, url


# ── Paging, filter, CSV ──────────────────────────────────────────────────────

def test_fifty_rows_a_page_with_filter_and_sort(with_2fa, db):
    for i in range(60):
        db.execute("INSERT INTO schema_meta (name, value) VALUES (?, ?)", (f"k{i:02d}", "v"))
    db.commit()
    page1 = with_2fa.get("/settings/data/schema_meta?sort=name&dir=asc").text
    assert "k00" in page1 and "k49" in page1 and "k50" not in page1 and "Page 1 of 2" in page1
    page2 = with_2fa.get("/settings/data/schema_meta?sort=name&dir=asc&page=2").text
    assert "k59" in page2 and "k00" not in page2
    filtered = with_2fa.get("/settings/data/schema_meta?q=k5").text
    assert "k55" in filtered and "k44" not in filtered


def test_csv_exports_the_current_view_and_neutralises_formulas(with_2fa, db):
    db.execute("INSERT INTO schema_meta (name, value) VALUES ('evil', '=HYPERLINK(1)')")
    db.execute("INSERT INTO schema_meta (name, value) VALUES ('plain', 'ok')")
    db.commit()
    r = with_2fa.get("/settings/data/schema_meta.csv?q=evil")
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0] == "name,value" and len(lines) == 2
    assert "'=HYPERLINK(1)" in lines[1]


# ── Lineage and audit ────────────────────────────────────────────────────────

def test_each_fact_links_to_its_lineage_with_history(with_2fa, db):
    r = with_2fa.post("/analyser/companies", data={"name": "Fictional Lineage Co",
                                                   "company_type": "manufacturer"}, follow_redirects=False)
    cid = r.headers["location"].rsplit("/", 1)[1]
    r = with_2fa.post(f"/analyser/c/{cid}/analyses", data={
        "name": "FY", "current_label": "FY2025", "prior_label": "FY2024", "unit": "million"},
        follow_redirects=False)
    aid = r.headers["location"].rsplit("/", 1)[1]
    with_2fa.post(f"/analyser/a/{aid}/facts", data={"unit": "million", "current:revenue": "12"})
    with_2fa.post(f"/analyser/a/{aid}/facts", data={"unit": "million", "current:revenue": "13"})
    fid = db.execute("SELECT id FROM facts WHERE field = 'revenue'").fetchone()[0]

    table = with_2fa.get("/settings/data/facts").text
    assert f'/settings/data/facts/{fid}/lineage' in table
    page = with_2fa.get(f"/settings/data/facts/{fid}/lineage").text
    for text in ("Revenue (net sales)", "PKR 13,000,000", "entered", "Fictional Lineage Co",
                 "FY2025", "admin", "12000000", "13000000"):
        assert text in page, text


def test_every_view_is_audit_logged(with_2fa, db):
    n = _views(db)
    with_2fa.get("/settings/data")
    with_2fa.get("/settings/data/users")
    with_2fa.get("/settings/data/users.csv")
    assert _views(db) == n + 3
    last = db.execute("SELECT user_id, details FROM audit_log WHERE event_type = 'data_page_viewed' "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    assert last["user_id"] == "admin" and '"view": "csv"' in last["details"]


def test_hidden_columns_show_as_hidden(with_2fa):
    page = with_2fa.get("/settings/data/users").text
    for col in ("password_hash", "totp_secret", "master_salt"):
        assert f'<th class="col-hidden">{col}</th>' in page
    assert '<td class="col-hidden">hidden</td>' in page
    csv_lines = with_2fa.get("/settings/data/users.csv").text.splitlines()
    header, row = csv_lines[0].split(","), csv_lines[1].split(",")
    assert row[header.index("password_hash")] == "hidden"
    assert row[header.index("username")] == "admin"
