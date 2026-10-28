# Security

ShaFin is a single-owner application that runs on your own machine in Docker. This page
says what protects your data, what does not, and what must never change.

## What protects what

| Data | Protection | Post-quantum? |
|---|---|---|
| The database file and its backups | SQLCipher, AES-256, keyed by `DB_MASTER_PASSWORD` | No. AES-256 is a classical cipher. |
| Generated reports on disk | AES-256-GCM with a per-company key | The per-company key is derived with an ML-KEM-768 + X25519 hybrid secret, but the file cipher itself is AES-256-GCM. |
| Report authenticity | ML-DSA-65 signature (NIST FIPS 204) over the PDF, checked before every download | Yes. |
| Owner password | Argon2id hash | Not applicable. |
| Sessions | Random 288-bit token; the server stores only its SHA-256 and an AES-256-GCM-encrypted payload; bound to IP and user agent | No. |
| Audit log | SHA-256 hash chain; any edit or deletion breaks the chain | Not applicable. |
| Transport | TLS with a self-signed certificate generated on first run | No. |

ShaFin never claims that the database or its backups are post-quantum. Only the report
signatures (ML-DSA-65) and the hybrid key encapsulation (ML-KEM-768, combined with X25519)
are post-quantum algorithms.

## Fails closed

- **No liboqs, no start.** `require_pqc()` runs before anything else, in `main.py` and in the
  app's startup. If the liboqs shared library, liboqs-python, ML-KEM-768 or ML-DSA-65 is
  missing, ShaFin prints the reason and exits.
  ShaFin looks for the liboqs library before importing liboqs-python, because
  liboqs-python would otherwise try to download and build liboqs at run time.
- **Only ML-DSA-65 signs.** `sign_document` refuses any other algorithm and
  `verify_signature` returns false for any other algorithm.
- **No classical-only company keys.** A company key is
  `HKDF(hybrid secret || HKDF(master key, salt))`. If the hybrid material is missing or
  does not decrypt, key derivation raises; it never falls back to a weaker key.
- **Self-test.** At startup ShaFin checks AES-256-GCM, Argon2id, HKDF, the hybrid KEM and
  ML-DSA. Any failure stops the startup.
- **Database.** A wrong `DB_MASTER_PASSWORD` or a missing SQLCipher stops the startup;
  ShaFin never opens an unencrypted database.

## Key-derivation labels: never change them after first use

These byte strings are inputs to key derivation. Changing one after a database has been
created makes every key derived from it different, so existing reports and sessions can
no longer be decrypted. From the first install onwards they are fixed.

| Label | Where | Derives |
|---|---|---|
| `shafin-client-key-v1` | `security/crypto.py` | the classical half of each company key |
| `shafin-client-key-v2` | `security/crypto.py` | each company key from the hybrid secret and the classical half |
| `shafin-hybrid-kem-v1` | `security/pqc.py` | the hybrid ML-KEM-768 + X25519 shared secret |
| `shafin-session-key-v1` | `security/auth.py` | the session payload key from `APP_SECRET_KEY` |

Two related names are not key-derivation inputs but should also stay fixed:

- The TOTP issuer `ShaFin` (`security/auth.py`). Changing it does not break existing codes,
  but authenticator apps would list a new name after 2FA is set up again.
- The TLS certificate names `shafin.crt`, `shafin.key` and `shafin.local`
  (`security/tls.py`). Changing them makes ShaFin generate a new certificate, which the
  browser must trust again.

To introduce a new derivation, add a new label with a new version suffix and migrate the
data; never edit an existing label.

## Health endpoints

- `GET /healthz` is public and minimal: `{"status": "ok"}` or `{"status": "unavailable"}`
  (HTTP 503). It reveals no version, path or error text. Docker's health check uses it.
- `GET /health` needs the owner's login and shows the full status: database, liboqs version
  and algorithms, the security self-test, the signing key, the audit chain and backups.

## Reporting a vulnerability

Please report security problems privately to the repository owner rather than in a
public issue.
