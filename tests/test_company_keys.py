"""Per-company keys use the ML-KEM-768 + X25519 hybrid secret and never fall back."""

import pytest

from database.companies import create_company
from security.crypto import CompanyKeyError, derive_company_classical_key, derive_company_key
from security.keys import get_company_key, get_master_key


def _row(db, cid):
    return dict(db.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone())


def test_company_key_is_deterministic_and_not_the_classical_key(db, owner):
    c = create_company("Fictional Mills Ltd", "manufacturer", None, "admin")
    k1, k2 = get_company_key(c["id"]), get_company_key(c["id"])
    assert k1 == k2 and len(k1) == 32
    assert k1 != derive_company_classical_key(get_master_key(), bytes(_row(db, c["id"])["salt"]))


def test_two_companies_get_different_keys(owner):
    a = create_company("Alpha Fictional", "manufacturer", None, "admin")
    b = create_company("Beta Fictional", "bank", None, "admin")
    assert get_company_key(a["id"]) != get_company_key(b["id"])


def test_corrupt_ciphertext_raises_instead_of_falling_back(db, owner):
    c = create_company("Fictional Mills Ltd", "manufacturer", None, "admin")
    row = _row(db, c["id"])
    row["kem_ciphertext"] = bytes(row["kem_ciphertext"])[:-1]
    with pytest.raises(Exception):
        derive_company_key(get_master_key(), row)


def test_missing_key_material_raises(db, owner):
    c = create_company("Fictional Mills Ltd", "manufacturer", None, "admin")
    row = _row(db, c["id"])
    row["kem_private_key_enc"] = None
    with pytest.raises(CompanyKeyError):
        derive_company_key(get_master_key(), row)


def test_wrong_master_key_raises(db, owner):
    c = create_company("Fictional Mills Ltd", "manufacturer", None, "admin")
    with pytest.raises(CompanyKeyError):
        derive_company_key(b"\x01" * 32, _row(db, c["id"]))


def test_no_company_without_an_owner_account(db):
    with pytest.raises(CompanyKeyError):
        create_company("Fictional Mills Ltd", "manufacturer", None, "admin")
