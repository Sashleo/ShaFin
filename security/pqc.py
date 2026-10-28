"""
security/pqc.py - Post-quantum cryptography through liboqs. Fails closed.

- ML-KEM-768 + X25519 hybrid key encapsulation (NIST FIPS 203 for ML-KEM) for the
  per-company encryption keys.
- ML-DSA-65 signatures for reports (NIST FIPS 204).

require_pqc() runs before the app starts and raises
PQCUnavailable when the liboqs shared library, liboqs-python, ML-KEM-768 or
ML-DSA-65 is missing, and every function here raises the same error.

The liboqs shared library is looked up before `import oqs`, because
liboqs-python tries to download and build liboqs when the library is missing,
and ShaFin never downloads anything at run time.
"""

from __future__ import annotations

import ctypes.util
import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)

KEM_ALGORITHM = "ML-KEM-768"
SIG_ALGORITHM = "ML-DSA-65"
X25519_PUBLIC_LEN = 32

# Part of key derivation: never change after first use (docs/SECURITY.md).
_HYBRID_KEM_INFO = b"shafin-hybrid-kem-v1"


class PQCUnavailable(RuntimeError):
    """liboqs or one of the required algorithms is not available."""


def _oqs():
    """Return the oqs module, or raise PQCUnavailable. Never triggers a download."""
    if ctypes.util.find_library("oqs") is None:
        raise PQCUnavailable(
            "The liboqs shared library was not found. ShaFin signs reports with "
            f"{SIG_ALGORITHM} and derives company keys with {KEM_ALGORITHM}; it does not "
            "run without them. Use the Docker image, which builds liboqs."
        )
    try:
        import oqs
    except ImportError as e:
        raise PQCUnavailable(
            f"liboqs-python could not be imported ({e}). Use the Docker image."
        ) from e
    return oqs


def require_pqc() -> str:
    """Check liboqs, ML-KEM-768 and ML-DSA-65. Returns the liboqs version."""
    oqs = _oqs()
    if SIG_ALGORITHM not in oqs.get_enabled_sig_mechanisms():
        raise PQCUnavailable(f"liboqs was built without {SIG_ALGORITHM}.")
    if KEM_ALGORITHM not in oqs.get_enabled_kem_mechanisms():
        raise PQCUnavailable(f"liboqs was built without {KEM_ALGORITHM}.")
    return oqs.oqs_version()


# ── ML-KEM-768 + X25519 hybrid key encapsulation ─────────────────────────────

@dataclass
class HybridKeyPair:
    kem_public_key: bytes
    kem_private_key: bytes
    x25519_public_key: bytes
    x25519_private_key: bytes


def generate_hybrid_keypair() -> HybridKeyPair:
    oqs = _oqs()
    with oqs.KeyEncapsulation(KEM_ALGORITHM) as kem:
        kem_public = kem.generate_keypair()
        kem_private = kem.export_secret_key()
    x_priv = X25519PrivateKey.generate()
    return HybridKeyPair(
        kem_public_key=kem_public,
        kem_private_key=kem_private,
        x25519_public_key=x_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
        x25519_private_key=x_priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()),
    )


def _combine(kem_secret: bytes, x_secret: bytes, eph_public: bytes, recipient_x_public: bytes) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HYBRID_KEM_INFO + eph_public + recipient_x_public,
    )
    return hkdf.derive(kem_secret + x_secret)


def hybrid_encapsulate(kem_public_key: bytes, x25519_public_key: bytes) -> tuple[bytes, bytes]:
    """Return (ciphertext, shared_secret). ciphertext = ML-KEM ciphertext || X25519 ephemeral key."""
    oqs = _oqs()
    with oqs.KeyEncapsulation(KEM_ALGORITHM) as kem:
        kem_ct, kem_secret = kem.encap_secret(kem_public_key)
    eph = X25519PrivateKey.generate()
    eph_public = eph.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    x_secret = eph.exchange(X25519PublicKey.from_public_bytes(x25519_public_key))
    return kem_ct + eph_public, _combine(kem_secret, x_secret, eph_public, x25519_public_key)


def hybrid_decapsulate(keypair: HybridKeyPair, ciphertext: bytes) -> bytes:
    """Recover the shared secret from hybrid_encapsulate's ciphertext. Raises on any mismatch."""
    oqs = _oqs()
    kem_ct, eph_public = ciphertext[:-X25519_PUBLIC_LEN], ciphertext[-X25519_PUBLIC_LEN:]
    with oqs.KeyEncapsulation(KEM_ALGORITHM, secret_key=keypair.kem_private_key) as kem:
        if len(kem_ct) != kem.details["length_ciphertext"]:
            raise ValueError("hybrid ciphertext has the wrong length")
        kem_secret = kem.decap_secret(kem_ct)
    x_priv = X25519PrivateKey.from_private_bytes(keypair.x25519_private_key)
    x_secret = x_priv.exchange(X25519PublicKey.from_public_bytes(eph_public))
    return _combine(kem_secret, x_secret, eph_public, keypair.x25519_public_key)


# ── ML-DSA-65 report signing ─────────────────────────────────────────────────

@dataclass
class SigningKeyPair:
    algorithm: str
    public_key: bytes
    private_key: bytes
    fingerprint: str   # first 16 hex chars of SHA-256(public key)


def generate_signing_keypair() -> SigningKeyPair:
    oqs = _oqs()
    with oqs.Signature(SIG_ALGORITHM) as sig:
        public_key = sig.generate_keypair()
        private_key = sig.export_secret_key()
    return SigningKeyPair(
        algorithm=SIG_ALGORITHM,
        public_key=public_key,
        private_key=private_key,
        fingerprint=hashlib.sha256(public_key).hexdigest()[:16].upper(),
    )


def sign_document(document: bytes, private_key: bytes, algorithm: str) -> bytes:
    """Sign with ML-DSA-65. Any other algorithm is refused."""
    if algorithm != SIG_ALGORITHM:
        raise ValueError(f"refusing to sign with {algorithm!r}: only {SIG_ALGORITHM} is allowed")
    oqs = _oqs()
    with oqs.Signature(SIG_ALGORITHM, secret_key=private_key) as sig:
        return sig.sign(document)


def verify_signature(document: bytes, signature: bytes, public_key: bytes, algorithm: str) -> bool:
    """True only for a valid ML-DSA-65 signature. Any other algorithm is False."""
    if algorithm != SIG_ALGORITHM:
        return False
    oqs = _oqs()
    with oqs.Signature(SIG_ALGORITHM) as sig:
        return bool(sig.verify(document, signature, public_key))
