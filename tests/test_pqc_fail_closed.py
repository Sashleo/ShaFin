"""
security/pqc.py fails closed: no liboqs or no ML-DSA means no start, and every
signature ShaFin makes or accepts is ML-DSA-65.
"""

import ctypes.util
import re
import sys
from pathlib import Path

import pytest

import security.pqc as pqc
from security.pqc import PQCUnavailable, SIG_ALGORITHM, require_pqc

ROOT = Path(__file__).resolve().parent.parent


def _no_liboqs(monkeypatch):
    real = ctypes.util.find_library
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None if name == "oqs" else real(name))


# ── Startup refuses without liboqs or ML-DSA ─────────────────────────────────

def test_require_pqc_passes_with_liboqs():
    assert re.match(r"\d+\.\d+", require_pqc())


def test_require_pqc_fails_without_the_liboqs_library(monkeypatch):
    _no_liboqs(monkeypatch)
    with pytest.raises(PQCUnavailable, match="liboqs shared library was not found"):
        require_pqc()


def test_require_pqc_fails_without_liboqs_python(monkeypatch):
    monkeypatch.setitem(sys.modules, "oqs", None)   # makes `import oqs` raise ImportError
    with pytest.raises(PQCUnavailable, match="liboqs-python could not be imported"):
        require_pqc()


def test_require_pqc_fails_without_ml_dsa(monkeypatch):
    import oqs
    monkeypatch.setattr(oqs, "get_enabled_sig_mechanisms", lambda: ["SLH-DSA-SHA2-128s"])
    with pytest.raises(PQCUnavailable, match="ML-DSA-65"):
        require_pqc()


def test_app_startup_fails_without_liboqs(monkeypatch):
    from fastapi.testclient import TestClient
    from app import create_app
    _no_liboqs(monkeypatch)
    with pytest.raises(PQCUnavailable):
        with TestClient(create_app(), base_url="https://testserver"):
            pass


def test_main_exits_with_a_clear_error_without_liboqs(monkeypatch, capsys):
    import main
    _no_liboqs(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "FATAL" in err and "liboqs" in err and "will not start" in err


def test_every_pqc_function_refuses_without_liboqs(monkeypatch):
    _no_liboqs(monkeypatch)
    for call in (pqc.generate_signing_keypair, pqc.generate_hybrid_keypair):
        with pytest.raises(PQCUnavailable):
            call()


# ── Every signature is ML-DSA-65 ─────────────────────────────────────────────

def test_signing_keys_are_ml_dsa_65():
    kp = pqc.generate_signing_keypair()
    assert kp.algorithm == SIG_ALGORITHM == "ML-DSA-65"


def test_signature_is_a_real_ml_dsa_65_signature():
    import oqs
    kp = pqc.generate_signing_keypair()
    sig = pqc.sign_document(b"report bytes", kp.private_key, kp.algorithm)
    with oqs.Signature("ML-DSA-65") as independent:
        assert len(sig) == independent.details["length_signature"]
        assert independent.verify(b"report bytes", sig, kp.public_key)


def test_signing_with_another_algorithm_is_refused():
    kp = pqc.generate_signing_keypair()
    for algorithm in ("RSA-PSS-SHA256", "ML-DSA-44", "Ed25519", ""):
        with pytest.raises(ValueError, match="only ML-DSA-65"):
            pqc.sign_document(b"x", kp.private_key, algorithm)


def test_verification_under_another_algorithm_is_false():
    kp = pqc.generate_signing_keypair()
    sig = pqc.sign_document(b"x", kp.private_key, kp.algorithm)
    assert pqc.verify_signature(b"x", sig, kp.public_key, "ML-DSA-65") is True
    assert pqc.verify_signature(b"x", sig, kp.public_key, "RSA-PSS-SHA256") is False
    assert pqc.verify_signature(b"y", sig, kp.public_key, "ML-DSA-65") is False


def test_rsa_and_os_urandom_keys_appear_nowhere():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts or ".cache" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\brsa\b", text, re.IGNORECASE):
            offenders.append(f"{path.name}: RSA")
        if path.parent.name == "security" and "urandom" in text:
            offenders.append(f"{path.name}: os.urandom")
    assert offenders == []


# ── Hybrid KEM ───────────────────────────────────────────────────────────────

def test_hybrid_kem_round_trip():
    kp = pqc.generate_hybrid_keypair()
    ct, secret = pqc.hybrid_encapsulate(kp.kem_public_key, kp.x25519_public_key)
    assert len(secret) == 32
    assert pqc.hybrid_decapsulate(kp, ct) == secret


def test_hybrid_kem_rejects_a_truncated_ciphertext():
    kp = pqc.generate_hybrid_keypair()
    ct, _ = pqc.hybrid_encapsulate(kp.kem_public_key, kp.x25519_public_key)
    with pytest.raises(ValueError):
        pqc.hybrid_decapsulate(kp, ct[:-1])


def test_hybrid_secret_needs_the_x25519_half():
    kp = pqc.generate_hybrid_keypair()
    other = pqc.generate_hybrid_keypair()
    ct, secret = pqc.hybrid_encapsulate(kp.kem_public_key, kp.x25519_public_key)
    kp.x25519_private_key = other.x25519_private_key
    kp.x25519_public_key = other.x25519_public_key
    assert pqc.hybrid_decapsulate(kp, ct) != secret
