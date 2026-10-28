# ── ShaFin Dockerfile ─────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
# Build tools for liboqs and pysqlcipher3; SQLCipher; Pango/Cairo for WeasyPrint.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    cmake \
    ninja-build \
    libssl-dev \
    libffi-dev \
    sqlcipher \
    libsqlcipher-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libfontconfig1 \
    libglib2.0-0t64 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ── liboqs 0.16.0, minimal build (ML-KEM-768 + ML-DSA-65 only) ────────────────
# The source tarball is pinned by SHA-256; the build fails if it differs.
ARG LIBOQS_SHA256=162d5b510518ee5f285f82fa1f16402a885176e818bf1b1a4c3c91c9a2f01eae
RUN curl -fsSL https://github.com/open-quantum-safe/liboqs/archive/refs/tags/0.16.0.tar.gz \
        -o /tmp/liboqs.tar.gz \
    && echo "${LIBOQS_SHA256}  /tmp/liboqs.tar.gz" | sha256sum -c - \
    && mkdir /tmp/liboqs \
    && tar -xzf /tmp/liboqs.tar.gz -C /tmp/liboqs --strip-components=1 \
    && rm /tmp/liboqs.tar.gz \
    && cmake -S /tmp/liboqs -B /tmp/liboqs/build \
        -GNinja \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DBUILD_SHARED_LIBS=ON \
        -DOQS_BUILD_ONLY_LIB=ON \
        -DOQS_USE_OPENSSL=OFF \
        -DOQS_MINIMAL_BUILD="KEM_ml_kem_768;SIG_ml_dsa_65" \
    && cmake --build /tmp/liboqs/build --parallel 4 \
    && cmake --install /tmp/liboqs/build \
    && rm -rf /tmp/liboqs \
    && ldconfig

# ── Python dependencies (hash-locked) ─────────────────────────────────────────
COPY requirements-ci.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements-ci.txt

# ── Application ───────────────────────────────────────────────────────────────
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV LD_LIBRARY_PATH=/usr/local/lib

# ── Drop root: run as an unprivileged user (uid 10001) ────────────────────────
RUN useradd -m -u 10001 shafin \
    && mkdir -p /app/data \
    && chown -R shafin:shafin /app
USER shafin

EXPOSE 8000

# /healthz is public and says only "ok" or "unavailable". -k: self-signed certificate.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fk https://localhost:8000/healthz || exit 1

CMD ["python", "main.py"]
