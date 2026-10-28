"""
scripts/check_tracked.py — Every file the app loads by name must be in git.

Collects every template named in the Python code (TemplateResponse, get_template) and in
other templates ({% extends %}, {% include %}, {% import %}), every /static/ file named in
a template, and every file a stylesheet loads with url(...), then reports any of them
that `git ls-files` does not list. A file that exists on disk but is not tracked works
locally and is missing from every clone, image and release.

    python3 scripts/check_tracked.py        # exit 1 and a list if anything is missing
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_PY_TEMPLATE = re.compile(r"""["']([\w./-]+\.html)["']""")
_TPL_TEMPLATE = re.compile(r"""{%-?\s*(?:extends|include|import|from)\s+["']([\w./-]+)["']""")
_TPL_STATIC = re.compile(r"""/static/([\w./-]+)""")
_CSS_URL = re.compile(r"""url\(\s*["']?(?!data:|https?:|#)([^"')?#]+)""")


def tracked_files() -> set[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return set(out.stdout.splitlines())


def referenced_files(files: set[str]) -> dict[str, str]:
    """{referenced path: where it is referenced}, for the files given (repository paths)."""
    refs: dict[str, str] = {}
    for path in sorted(files):
        if path.startswith("tests/"):
            continue
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace") \
            if path.endswith((".py", ".html", ".css")) else ""
        if path.endswith(".py"):
            for name in _PY_TEMPLATE.findall(text):
                refs.setdefault(f"templates/{name}", path)
        elif path.endswith(".html"):
            for name in _TPL_TEMPLATE.findall(text):
                refs.setdefault(f"templates/{name}", path)
            for name in _TPL_STATIC.findall(text):
                refs.setdefault(f"static/{name}", path)
        elif path.endswith(".css"):
            for url in _CSS_URL.findall(text):
                # /static/... is served from static/; anything else is relative to the sheet.
                ref = url.lstrip("/") if url.startswith("/static/") else \
                    posixpath.normpath(posixpath.join(posixpath.dirname(path), url))
                refs.setdefault(ref, path)
    return refs


def missing(files: set[str]) -> list[str]:
    return [f"{ref}  (referenced in {where})"
            for ref, where in sorted(referenced_files(files).items()) if ref not in files]


def main() -> int:
    files = tracked_files()
    problems = missing(files)
    if problems:
        print("Referenced but not tracked by git:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    print(f"OK: all {len(referenced_files(files))} referenced templates and static files are tracked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
