"""
security/selftest.py — Cryptographic self-test run at startup.

Verifies that encryption round-trips, key derivation is deterministic,
the hybrid KEM and ML-DSA signing work. Startup refuses to continue on any failure.
"""

import structlog

log = structlog.get_logger()


def run_self_test() -> list[str]:
    """
    Run all cryptographic self-tests. Returns a list of failure messages.
    Empty list means all tests passed.
    """
    failures = []

    failures.extend(_test_aes_roundtrip())
    failures.extend(_test_argon2())
    failures.extend(_test_hkdf_determinism())
    failures.extend(_test_hybrid_kem_roundtrip())
    failures.extend(_test_signing_roundtrip())

    if failures:
        for f in failures:
            log.error("Security self-test FAILED", test=f)
    else:
        log.info("Security self-test passed")

    return failures


def _test_aes_roundtrip() -> list[str]:
    try:
        from security.crypto import encrypt_bytes, decrypt_bytes
        key = bytes(range(32))
        plaintext = b"self-test payload"
        ct = encrypt_bytes(plaintext, key)
        pt = decrypt_bytes(ct, key)
        if pt != plaintext:
            return ["AES-256-GCM round-trip: decrypted data does not match"]
        return []
    except Exception as e:
        return [f"AES-256-GCM round-trip: {e}"]


def _test_argon2() -> list[str]:
    try:
        from security.crypto import hash_password, verify_password
        h = hash_password("selftest")
        if not verify_password("selftest", h):
            return ["Argon2id: verification of correct password failed"]
        if verify_password("wrong", h):
            return ["Argon2id: verification of wrong password succeeded"]
        return []
    except Exception as e:
        return [f"Argon2id: {e}"]


def _test_hkdf_determinism() -> list[str]:
    try:
        from security.crypto import derive_company_classical_key
        master = bytes(range(32))
        salt = b"0" * 16
        k1 = derive_company_classical_key(master, salt)
        k2 = derive_company_classical_key(master, salt)
        if k1 != k2:
            return ["HKDF: same inputs produced different keys"]
        return []
    except Exception as e:
        return [f"HKDF: {e}"]


def _test_hybrid_kem_roundtrip() -> list[str]:
    try:
        from security.pqc import generate_hybrid_keypair, hybrid_decapsulate, hybrid_encapsulate
        kp = generate_hybrid_keypair()
        ct, secret = hybrid_encapsulate(kp.kem_public_key, kp.x25519_public_key)
        if hybrid_decapsulate(kp, ct) != secret:
            return ["Hybrid KEM round-trip: decapsulated secret does not match"]
        return []
    except Exception as e:
        return [f"Hybrid KEM round-trip: {e}"]


def _test_signing_roundtrip() -> list[str]:
    try:
        from security.pqc import generate_signing_keypair, sign_document, verify_signature
        kp = generate_signing_keypair()
        doc = b"self-test document"
        sig = sign_document(doc, kp.private_key, kp.algorithm)
        if not verify_signature(doc, sig, kp.public_key, kp.algorithm):
            return [f"Signing round-trip ({kp.algorithm}): verification failed"]
        if verify_signature(b"tampered", sig, kp.public_key, kp.algorithm):
            return [f"Signing round-trip ({kp.algorithm}): tampered doc accepted"]
        return []
    except Exception as e:
        return [f"Signing round-trip: {e}"]
