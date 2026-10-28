"""
Every template the code renders and every static file a template or stylesheet loads
must be tracked by git, or it is missing from every clone, image and release.

With git available (a developer checkout, and CI before the image is built) the check
uses `git ls-files`. Inside the Docker image there is no .git; the image is built from a
git checkout, so the files present are the tracked files and the same check applies.
"""

import shutil
from pathlib import Path

from scripts.check_tracked import ROOT, missing, referenced_files, tracked_files

_SKIP = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".cache"}


def _files() -> set[str]:
    if shutil.which("git") and (ROOT / ".git").exists():
        return tracked_files()
    files = set()
    for p in ROOT.rglob("*"):
        parts = p.relative_to(ROOT).parts
        # /data at the top is the runtime data volume, never part of the source.
        if p.is_file() and not _SKIP & set(parts[:-1]) and parts[0] != "data":
            files.add(p.relative_to(ROOT).as_posix())
    return files


def test_every_referenced_template_and_static_file_is_tracked():
    assert missing(_files()) == []


def test_the_check_sees_templates_static_files_and_fonts():
    refs = referenced_files(_files())
    for path in ("templates/data/index.html", "templates/base.html", "templates/report/report.html",
                 "static/js/htmx.min.js", "static/css/components.css"):
        assert path in refs, path
    assert any(r.startswith("static/fonts/") for r in refs)


def test_an_untracked_template_is_reported():
    files = _files() - {"templates/data/index.html"}
    assert any(m.startswith("templates/data/index.html") for m in missing(files))


def test_ci_runs_the_check_with_git():
    ci = (Path(ROOT) / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "scripts/check_tracked.py" in ci
