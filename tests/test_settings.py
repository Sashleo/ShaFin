"""Settings: password change, two-factor setup, the threshold table. All audited."""

import pyotp

from security.crypto import verify_password


def _events(db, kind):
    return db.execute("SELECT COUNT(*) FROM audit_log WHERE event_type = ?", (kind,)).fetchone()[0]


def test_settings_page_shows_thresholds_with_rationale_and_no_rates(logged_in):
    page = logged_in.get("/settings").text
    assert "Flag thresholds" in page and "current liabilities exceed current assets" in page
    for word in ("Risk-free", "Equity risk premium", "Terminal growth"):
        assert word not in page


def test_password_change_works(logged_in, db):
    r = logged_in.post("/settings/change-password", data={
        "current_password": "correct horse battery 9", "new_password": "New fictional pass 7",
        "confirm_password": "New fictional pass 7"})
    assert "Password updated" in r.text
    assert verify_password("New fictional pass 7", db.execute("SELECT password_hash FROM users").fetchone()[0])
    assert _events(db, "password_changed") == 1


def test_password_change_checks_the_current_password_and_policy(logged_in):
    r = logged_in.post("/settings/change-password", data={
        "current_password": "wrong", "new_password": "New fictional pass 7",
        "confirm_password": "New fictional pass 7"})
    assert "incorrect" in r.text
    r = logged_in.post("/settings/change-password", data={
        "current_password": "correct horse battery 9", "new_password": "password123",
        "confirm_password": "password123"})
    assert "Password updated" not in r.text


def test_two_factor_setup_confirm_and_disable(logged_in, db):
    r = logged_in.post("/settings/setup-totp")
    assert "data:image/png;base64," in r.text
    secret = db.execute("SELECT totp_secret_pending FROM users").fetchone()[0]
    r = logged_in.post("/settings/confirm-totp", data={"totp_code": pyotp.TOTP(secret).now()})
    assert "is on" in r.text
    row = db.execute("SELECT totp_enabled, totp_secret, totp_secret_pending FROM users").fetchone()
    assert (row[0], row[1], row[2]) == (1, secret, None)
    r = logged_in.post("/settings/disable-totp", data={"totp_code": pyotp.TOTP(secret).now()})
    assert "is off" in r.text
    assert db.execute("SELECT totp_enabled FROM users").fetchone()[0] == 0
    assert _events(db, "totp_enabled") == 1 and _events(db, "totp_disabled") == 1


def test_threshold_add_replace_delete_is_audited(logged_in, db):
    logged_in.post("/settings/thresholds", data={"company_type": "bank", "metric": "casa_share",
                                                  "op": ">=", "value": "50",
                                                  "rationale": "Stable funding base."})
    row = db.execute("SELECT * FROM thresholds WHERE metric = 'casa_share'").fetchone()
    assert (row["company_type"], row["op"], row["value"], row["updated_by"]) == ("bank", ">=", "50", "admin")
    logged_in.post("/settings/thresholds", data={"company_type": "bank", "metric": "casa_share",
                                                  "op": ">=", "value": "55",
                                                  "rationale": "Stable funding base."})
    assert db.execute("SELECT value FROM thresholds WHERE metric = 'casa_share'").fetchone()[0] == "55"
    logged_in.post(f"/settings/thresholds/{row['id']}/delete")
    assert db.execute("SELECT COUNT(*) FROM thresholds WHERE metric = 'casa_share'").fetchone()[0] == 0
    assert _events(db, "threshold_changed") == 3


def test_threshold_needs_a_rationale_and_a_metric_of_that_type(logged_in, db):
    r = logged_in.post("/settings/thresholds", data={"company_type": "bank", "metric": "casa_share",
                                                      "op": ">=", "value": "50", "rationale": " "},
                       follow_redirects=False)
    assert "threshold_error" in r.headers["location"]
    r = logged_in.post("/settings/thresholds", data={"company_type": "bank", "metric": "gross_margin",
                                                      "op": ">=", "value": "50", "rationale": "x"},
                       follow_redirects=False)
    assert "threshold_error" in r.headers["location"]
    assert db.execute("SELECT COUNT(*) FROM thresholds WHERE metric IN ('casa_share', 'gross_margin') "
                      "AND company_type = 'bank'").fetchone()[0] == 0


def test_flags_in_an_analysis_follow_the_threshold_table(logged_in, db):
    r = logged_in.post("/analyser/companies", data={"name": "Fictional Flag Co",
                                                    "company_type": "manufacturer"}, follow_redirects=False)
    cid = r.headers["location"].rsplit("/", 1)[1]
    r = logged_in.post(f"/analyser/c/{cid}/analyses", data={
        "name": "FY", "current_label": "FY2025", "prior_label": "FY2024", "unit": "rupees"},
        follow_redirects=False)
    aid = r.headers["location"].rsplit("/", 1)[1]
    logged_in.post(f"/analyser/a/{aid}/facts", data={"unit": "rupees", "current:current_assets": "90",
                                                     "current:current_liabilities": "100"})
    assert "Below 1.0, current liabilities exceed current assets." in logged_in.get(f"/analyser/a/{aid}").text
    logged_in.post("/settings/thresholds", data={"company_type": "manufacturer", "metric": "current_ratio",
                                                  "op": ">=", "value": "0.8",
                                                  "rationale": "Owner accepts a lower ratio."})
    page = logged_in.get(f"/analyser/a/{aid}").text
    assert "Owner accepts a lower ratio." in page and "1 of 1 thresholds met" in page
