"""
main.py — ShaFin application entry point.

Checks the post-quantum library first and refuses to start without it, then
generates a self-signed TLS certificate on first run and starts uvicorn with SSL
so all session cookies travel over an encrypted channel.

Run via Docker:
    docker compose up --build
"""

import sys

import uvicorn

from security.pqc import PQCUnavailable, require_pqc
from security.tls import ensure_tls_cert


def main():
    try:
        liboqs_version = require_pqc()
    except PQCUnavailable as e:
        print(f"\nFATAL: {e}\nShaFin will not start without post-quantum signing.\n", file=sys.stderr)
        sys.exit(1)

    try:
        cert_path, key_path = ensure_tls_cert()
    except RuntimeError as e:
        print(f"\n{e}\n", file=sys.stderr)
        sys.exit(1)

    print(f"ShaFin starting on https://localhost:8000 (liboqs {liboqs_version})")
    print(f"TLS certificate: {cert_path}")
    print("Note: the browser will show a self-signed certificate warning.")

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        ssl_certfile=cert_path,
        ssl_keyfile=key_path,
        workers=1,
        log_level="info",
        access_log=False,  # Structured logging via structlog
    )


if __name__ == "__main__":
    main()
