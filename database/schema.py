"""
database/schema.py — ShaFin schema.

users, sessions, audit_log, pqc_keys: the owner account and security.
companies:   one row per company, with its type and its hybrid key material.
analyses:    a named analysis of a company, with current and prior period labels and
             the reporting unit the figures are entered in.
facts:       one row per entered figure: whole rupees for money, a decimal text for
             counts and percentages; source is always 'entered'.
assumptions: per-analysis assumptions, each with a required source and date.
thresholds:  the owner's flag thresholds per company type, each with its rationale.
reports:     generated, signed, encrypted reports.
schema_meta: one-time setup markers.

Every statement is CREATE ... IF NOT EXISTS or a guarded insert, so run_migrations()
is safe to call on every start and never drops or restores a row.
"""

from datetime import datetime, timezone

import structlog
from database.connection import get_db

log = structlog.get_logger()

SCHEMA_VERSION = 1

TABLES = """
CREATE TABLE IF NOT EXISTS schema_meta (
    name            TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    totp_secret     TEXT,
    totp_secret_pending TEXT,
    totp_enabled    INTEGER NOT NULL DEFAULT 0,
    master_salt     BLOB,
    created_at      TEXT NOT NULL,
    last_login      TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash   TEXT    PRIMARY KEY,
    payload_enc  BLOB    NOT NULL,
    ip_ua_hash   TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    expires_at   TEXT    NOT NULL,
    last_seen    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    user_id     TEXT,
    company_id  TEXT,
    details     TEXT,
    ip_address  TEXT,
    timestamp   TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    entry_hash  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS pqc_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key_type        TEXT NOT NULL,
    algorithm       TEXT NOT NULL,
    public_key      BLOB NOT NULL,
    private_key_encrypted BLOB NOT NULL,
    fingerprint     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS companies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    company_type    TEXT NOT NULL
                    CHECK (company_type IN ('manufacturer', 'non_manufacturer', 'bank')),
    industry        TEXT,
    salt            BLOB NOT NULL,
    kem_public_key      BLOB NOT NULL,
    kem_private_key_enc BLOB NOT NULL,
    kem_ciphertext      BLOB NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analyses (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    name            TEXT NOT NULL,
    current_label   TEXT NOT NULL,
    prior_label     TEXT NOT NULL,
    unit            TEXT NOT NULL,
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analyses_company ON analyses(company_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS facts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id     TEXT NOT NULL REFERENCES analyses(id),
    period          TEXT NOT NULL CHECK (period IN ('current', 'prior')),
    field           TEXT NOT NULL,
    value_rupees    INTEGER,
    value_number    TEXT,
    unit            TEXT NOT NULL,
    entered_text    TEXT NOT NULL,
    page_ref        TEXT,
    source          TEXT NOT NULL DEFAULT 'entered' CHECK (source = 'entered'),
    saved_by        TEXT NOT NULL,
    saved_at        TEXT NOT NULL,
    UNIQUE (analysis_id, period, field),
    CHECK ((value_rupees IS NULL) <> (value_number IS NULL))
);

CREATE TABLE IF NOT EXISTS assumptions (
    analysis_id     TEXT NOT NULL REFERENCES analyses(id),
    name            TEXT NOT NULL,
    value           TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (length(trim(source)) > 0),
    as_of           TEXT NOT NULL CHECK (length(as_of) = 10),
    saved_by        TEXT NOT NULL,
    saved_at        TEXT NOT NULL,
    PRIMARY KEY (analysis_id, name)
);

CREATE TABLE IF NOT EXISTS thresholds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_type    TEXT NOT NULL,
    metric          TEXT NOT NULL,
    op              TEXT NOT NULL CHECK (op IN ('>=', '>', '<=', '<')),
    value           TEXT NOT NULL,
    rationale       TEXT NOT NULL,
    updated_by      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (company_type, metric)
);

CREATE TABLE IF NOT EXISTS reports (
    id                  TEXT PRIMARY KEY,
    company_id          TEXT NOT NULL REFERENCES companies(id),
    analysis_id         TEXT NOT NULL REFERENCES analyses(id),
    title               TEXT NOT NULL,
    pdf_path            TEXT NOT NULL,
    docx_path           TEXT NOT NULL,
    pdf_signature_path  TEXT NOT NULL,
    docx_signature_path TEXT NOT NULL,
    signing_algo        TEXT NOT NULL,
    signing_fingerprint TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
"""

# The owner's starting flag thresholds, written once on first start. They are flags,
# not rates: Settings shows each with its rationale, and the owner can edit or delete
# them; a deleted threshold is not recreated.
STARTING_THRESHOLDS = [
    # (company types, metric, op, value, rationale)
    (("manufacturer", "non_manufacturer"), "current_ratio", ">=", "1.0",
     "Below 1.0, current liabilities exceed current assets."),
    (("manufacturer", "non_manufacturer"), "interest_coverage", ">=", "2.0",
     "Below 2x, a halving of operating profit would leave finance cost uncovered."),
    (("manufacturer", "non_manufacturer"), "debt_to_equity", "<=", "2.0",
     "Above 2x, lenders fund more than twice what shareholders have invested."),
    (("manufacturer", "non_manufacturer"), "net_margin", ">", "0",
     "A net loss for the year."),
    (("manufacturer", "non_manufacturer", "bank"), "roe", ">", "0",
     "Shareholders' equity earned nothing or lost value this year."),
    (("bank",), "car_reported", ">=", "11.5",
     "The minimum capital adequacy ratio including the capital conservation buffer; "
     "check it against the regulator's current requirement and edit it if it has changed."),
    (("bank",), "npl_ratio", "<=", "10",
     "Above this, a tenth or more of the loan book is not performing."),
    (("bank",), "coverage", ">=", "80",
     "Below this, a material part of the non-performing loans is not provided for."),
    (("bank",), "cost_to_income", "<=", "60",
     "Above this, operating costs absorb most of the income before provisions."),
]


def run_migrations() -> None:
    """Create every missing table; write the starting thresholds on the first start only."""
    db = get_db()
    db.executescript(TABLES)
    if not db.execute("SELECT 1 FROM schema_meta WHERE name = 'thresholds_seeded'").fetchone():
        now = datetime.now(timezone.utc).isoformat()
        for types, metric, op, value, rationale in STARTING_THRESHOLDS:
            for company_type in types:
                db.execute(
                    "INSERT OR IGNORE INTO thresholds "
                    "(company_type, metric, op, value, rationale, updated_by, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'setup', ?)",
                    (company_type, metric, op, value, rationale, now),
                )
        db.execute("INSERT INTO schema_meta (name, value) VALUES ('thresholds_seeded', ?)", (now,))
    db.commit()
    log.info("Database schema ready", version=SCHEMA_VERSION)
