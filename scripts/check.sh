#!/usr/bin/env bash
# scripts/check.sh - ShaFin's quality gate. Runs inside the Docker image, which has
# liboqs and SQLCipher; CI runs it with networking disabled.
#
#   docker run --rm --network none -e APP_SECRET_KEY=... -e DB_MASTER_PASSWORD=... \
#       shafin:ci bash scripts/check.sh

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Calculation tests (hand-computed vectors, docs/CALCULATIONS.md)"
pytest tests/calculations -q --tb=short

echo ""
echo "==> All tests"
pytest -q --tb=short

echo ""
echo "==> Template syntax check (Jinja2 parse)"
python - <<'PY'
import os, sys
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
errors, count = [], 0
for root, _, files in os.walk("templates"):
    for f in files:
        if not f.endswith(".html"):
            continue
        count += 1
        path = os.path.join(root, f)
        try:
            env.parse(open(path, encoding="utf-8").read())
        except TemplateSyntaxError as e:
            errors.append(f"  {path}: {e}")
if errors:
    print("TEMPLATE ERRORS:")
    print("\n".join(errors))
    sys.exit(1)
print(f"  All templates OK ({count} files)")
PY

echo ""
echo "==> ruff (F401 unused import, F841 unused var, F811 redefinition, ERA001 commented code)"
python -m ruff check --select F401,F841,F811,ERA001 .

echo ""
echo "==> vulture (dead code, min confidence 80)"
# Exclude patterns are globs: a bare "data" would also skip database/ and routers/data.py.
python -m vulture . --min-confidence 80 --exclude "*/.cache/*,*/__pycache__/*" \
    --ignore-names cls \
    --ignore-decorators "@router.get,@router.post,@app.get,@app.exception_handler,@field_validator,@pytest.fixture"

echo ""
echo "All checks passed."
