"""
Reports are signed with ML-DSA-65, stored encrypted, and refused when the signature
does not match. Real liboqs, WeasyPrint, python-docx and AES-256-GCM.
"""

from datetime import date

import pytest

from reports.signer import ensure_signing_key, sign_report, verify_report
from security.keys import get_master_key


def test_signing_key_is_stored_as_ml_dsa_65(db, owner):
    info = ensure_signing_key(get_master_key())
    row = db.execute("SELECT algorithm, fingerprint FROM pqc_keys WHERE is_active=1").fetchone()
    assert row["algorithm"] == info["algorithm"] == "ML-DSA-65"
    assert row["fingerprint"] == info["fingerprint"]


def test_ensure_signing_key_is_idempotent(db, owner):
    a = ensure_signing_key(get_master_key())
    b = ensure_signing_key(get_master_key())
    assert a["fingerprint"] == b["fingerprint"]
    assert db.execute("SELECT COUNT(*) FROM pqc_keys").fetchone()[0] == 1


def test_sign_then_verify_roundtrip(owner):
    mk = get_master_key()
    ensure_signing_key(mk)
    sig, err = sign_report(b"%PDF fictional report", mk)
    assert err is None
    valid, msg = verify_report(b"%PDF fictional report", sig)
    assert valid is True and "ML-DSA-65" in msg


def test_tampered_document_fails_verification(owner):
    mk = get_master_key()
    ensure_signing_key(mk)
    sig, _ = sign_report(b"Original report content.", mk)
    valid, _ = verify_report(b"Tampered report content.", sig)
    assert valid is False


def test_a_non_ml_dsa_key_is_never_used(db, owner):
    mk = get_master_key()
    ensure_signing_key(mk)
    db.execute("UPDATE pqc_keys SET algorithm = 'RSA-PSS-SHA256'")
    sig, err = sign_report(b"doc", mk)
    assert sig is None and "only ML-DSA-65" in err
    info = ensure_signing_key(mk)             # retired and replaced
    assert info["algorithm"] == "ML-DSA-65"
    assert db.execute("SELECT COUNT(*) FROM pqc_keys WHERE is_active = 1").fetchone()[0] == 1


# ── End to end through the web layer ─────────────────────────────────────────

@pytest.fixture
def report(logged_in, reports_dir, db):
    r = logged_in.post("/analyser/companies", data={"name": "Fictional Report Co",
                                                    "company_type": "manufacturer"}, follow_redirects=False)
    cid = r.headers["location"].rsplit("/", 1)[1]
    r = logged_in.post(f"/analyser/c/{cid}/analyses", data={
        "name": "FY", "current_label": "FY2025", "prior_label": "FY2024", "unit": "thousand"},
        follow_redirects=False)
    aid = r.headers["location"].rsplit("/", 1)[1]
    logged_in.post(f"/analyser/a/{aid}/facts", data={"unit": "thousand", "current:revenue": "1000",
                                                     "prior:revenue": "900"})
    r = logged_in.post(f"/analyser/a/{aid}/report", follow_redirects=False)
    assert r.status_code == 303
    row = dict(db.execute("SELECT * FROM reports").fetchone())
    assert row["pdf_path"].startswith(str(reports_dir))
    return row


def test_report_files_are_encrypted_and_signed(report):
    with open(report["pdf_path"], "rb") as f:
        stored = f.read()
    assert not stored.startswith(b"%PDF")              # encrypted at rest
    assert report["signing_algo"] == "ML-DSA-65"


@pytest.mark.parametrize("kind, magic", [("pdf", b"%PDF"), ("docx", b"PK")])
def test_download_verifies_then_serves(logged_in, report, kind, magic, db):
    r = logged_in.get(f"/reports/{report['id']}/{kind}")
    assert r.status_code == 200 and r.content.startswith(magic)
    assert r.headers["x-report-signature"] == "verified ML-DSA-65"
    assert db.execute("SELECT COUNT(*) FROM audit_log WHERE event_type = 'report_downloaded'").fetchone()[0] == 1


@pytest.mark.parametrize("kind", ["pdf", "docx"])
def test_download_refuses_on_invalid_signature(logged_in, report, kind):
    path = report[f"{kind}_signature_path"]
    with open(path, "rb") as f:
        sig = bytearray(f.read())
    sig[10] ^= 0xFF
    with open(path, "wb") as f:
        f.write(bytes(sig))
    r = logged_in.get(f"/reports/{report['id']}/{kind}")
    assert r.status_code == 409
    assert b"%PDF" not in r.content and "signature does not match" in r.text


def test_signature_file_verifies_independently_with_liboqs(logged_in, report):
    import oqs
    pdf = logged_in.get(f"/reports/{report['id']}/pdf").content
    sig = logged_in.get(f"/reports/{report['id']}/pdf.sig").content
    pub = logged_in.get("/reports/signing-key.pub").content
    with oqs.Signature("ML-DSA-65") as verifier:
        assert verifier.verify(pdf, sig, pub)


def test_report_prints_the_assumption_table(owner):
    from database.analyses import (create_analysis, get_analysis, load_assumptions, load_facts,
                                   save_assumptions)
    from database.companies import create_company, get_company
    from reports.content import build_report_model
    from reports.pdf_renderer import render_html
    from routers.analyser import charts_for, run_analysis

    c = create_company("Fictional Print Co", "non_manufacturer", None, "admin")
    aid = create_analysis(c["id"], "FY", "FY2025", "FY2024", "thousand", "admin")
    save_assumptions(aid, {"beta": ("1.15", "Five-year weekly regression", date.today().isoformat())},
                     "admin")
    a, co = get_analysis(aid), get_company(c["id"])
    result = run_analysis(a, co)
    model = build_report_model(a, co, result, load_facts(aid), load_assumptions(aid),
                               charts_for(a, result), {"algorithm": "ML-DSA-65", "fingerprint": "ABC"})
    html = render_html(model, "now")
    for text in ("Assumptions", "Beta", "1.15x", "Five-year weekly regression",
                 date.today().isoformat(), "not investment advice", "Required: Risk-free rate"):
        assert text in html, text
