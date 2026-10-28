"""
security/crypto.py — Core cryptographic operations.

Provides:
- AES-256-GCM authenticated encryption/decryption
- Argon2id password hashing and master-key derivation
- HKDF per-company key derivation (combined with the ML-KEM-768 + X25519 hybrid secret)
- The hybrid key material each company key is derived from

AES-256-GCM is a classical cipher; ShaFin does not describe it as post-quantum.
"""

import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

import structlog

log = structlog.get_logger()

# ── Argon2id parameters (OWASP recommended for sensitive apps) ────────────────
# Memory: 64MB, iterations: 3, parallelism: 4
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,   # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    encoding="utf-8",
)

# ── Key sizes ─────────────────────────────────────────────────────────────────
AES_KEY_SIZE    = 32   # 256 bits
NONCE_SIZE      = 12   # 96 bits for AES-GCM
SALT_SIZE       = 32   # 256 bits
HKDF_KEY_SIZE   = 32   # 256 bits


class CompanyKeyError(RuntimeError):
    """A company key could not be derived. Never answered with a weaker key."""


def generate_salt() -> bytes:
    """Generate a cryptographically secure random salt."""
    return secrets.token_bytes(SALT_SIZE)


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.
    Returns the full Argon2 hash string (includes params and salt).
    """
    return _ph.hash(password)


def verify_password(password: str, hash_str: str) -> bool:
    """
    Verify a password against an Argon2id hash.
    Returns True if correct, False otherwise.
    Never raises — safe to use in auth flows.
    """
    try:
        return _ph.verify(hash_str, password)
    except (VerifyMismatchError, VerificationError):
        return False


def derive_master_key(password: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit master key from a password using Argon2id.
    This key is used to derive per-company keys via HKDF.

    Args:
        password: The master password
        salt: A stored salt (load from database on startup)

    Returns:
        32-byte master key
    """
    # Use argon2-cffi's low-level interface for raw key derivation
    from argon2.low_level import hash_secret_raw, Type
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        type=Type.ID,
    )


def derive_company_classical_key(master_key: bytes, company_salt: bytes) -> bytes:
    """
    Derive a unique encryption key for a company using HKDF (the classical half of its key).

    Each company has its own salt (stored in the database).
    Destroying the salt makes the company's reports irrecoverable.

    Args:
        master_key: The application master key
        company_salt: The company's salt

    Returns:
        32-byte key
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=HKDF_KEY_SIZE,
        salt=company_salt,
        info=b"shafin-client-key-v1",   # fixed label: see docs/SECURITY.md
        backend=default_backend(),
    )
    return hkdf.derive(master_key)


def encrypt(plaintext: str, key: bytes) -> bytes:
    """
    Encrypt a string using AES-256-GCM.

    Returns: nonce (12 bytes) + ciphertext + tag (16 bytes)
    The nonce is prepended to the ciphertext for storage.
    AES-GCM provides authenticated encryption — detects tampering.
    """
    if not plaintext:
        return b""
    nonce = secrets.token_bytes(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt(ciphertext: bytes, key: bytes) -> Optional[str]:
    """
    Decrypt AES-256-GCM ciphertext.

    Args:
        ciphertext: nonce + encrypted data (from encrypt())
        key: The AES-256 key

    Returns:
        Decrypted string, or None if decryption fails (wrong key or tampered)
    """
    if not ciphertext:
        return ""
    try:
        nonce = ciphertext[:NONCE_SIZE]
        data  = ciphertext[NONCE_SIZE:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, data, None)
        return plaintext.decode("utf-8")
    except Exception:
        log.warning("Decryption failed — wrong key or tampered data")
        return None


def derive_company_key(master_key: bytes, company_row: dict) -> bytes:
    """
    Derive a company's AES-256 key: HKDF(hybrid KEM secret || classical HKDF key).

    The hybrid secret comes from decapsulating the stored ML-KEM-768 + X25519
    ciphertext with the company's private keys, which are stored encrypted under
    the master key. Fails closed: any missing column, decryption failure or
    decapsulation failure raises CompanyKeyError. There is no classical-only key.
    """
    import json
    from security.pqc import HybridKeyPair, hybrid_decapsulate

    salt = company_row.get("salt")
    ciphertext = company_row.get("kem_ciphertext")
    private_enc = company_row.get("kem_private_key_enc")
    if not salt or not ciphertext or not private_enc:
        raise CompanyKeyError(f"company {company_row.get('id')} has no hybrid key material")
    salt = bytes(salt)

    bundle_json = decrypt(bytes(private_enc), master_key)
    if not bundle_json:
        raise CompanyKeyError("company private keys could not be decrypted with the master key")
    bundle = json.loads(bundle_json)
    keypair = HybridKeyPair(
        kem_public_key=b"",
        kem_private_key=bytes.fromhex(bundle["kem_private"]),
        x25519_public_key=bytes.fromhex(bundle["x25519_public"]),
        x25519_private_key=bytes.fromhex(bundle["x25519_private"]),
    )
    hybrid_secret = hybrid_decapsulate(keypair, bytes(ciphertext))

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=HKDF_KEY_SIZE,
        salt=salt,
        info=b"shafin-client-key-v2",   # fixed label: see docs/SECURITY.md
        backend=default_backend(),
    )
    return hkdf.derive(hybrid_secret + derive_company_classical_key(master_key, salt))


def new_company_key_material(master_key: bytes) -> dict:
    """Generate a company's hybrid key material: public key, ciphertext, encrypted private keys."""
    import json
    from security.pqc import generate_hybrid_keypair, hybrid_encapsulate

    keypair = generate_hybrid_keypair()
    ciphertext, _ = hybrid_encapsulate(keypair.kem_public_key, keypair.x25519_public_key)
    bundle = json.dumps({
        "kem_private": keypair.kem_private_key.hex(),
        "x25519_public": keypair.x25519_public_key.hex(),
        "x25519_private": keypair.x25519_private_key.hex(),
    })
    return {
        "kem_public_key": keypair.kem_public_key,
        "kem_ciphertext": ciphertext,
        "kem_private_key_enc": encrypt(bundle, master_key),
    }


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """Encrypt raw bytes (for document storage)."""
    if not data:
        return b""
    nonce = secrets.token_bytes(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt_bytes(ciphertext: bytes, key: bytes) -> Optional[bytes]:
    """Decrypt raw bytes (for document retrieval)."""
    if not ciphertext:
        return b""
    try:
        nonce = ciphertext[:NONCE_SIZE]
        data  = ciphertext[NONCE_SIZE:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, data, None)
    except Exception:
        log.warning("Bytes decryption failed")
        return None
