"""Repo-level regression guards (fmb edge suite).

Cheap invariants that have broken before or would silently break installers:
version drift between ``pyproject.toml`` and ``__version__``, the packaged copy
of SKILL.md, the skill frontmatter, ignore rules for local artifacts, and
credential-shaped strings in shipped code.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import desktop_harness  # noqa: E402


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert match, "pyproject.toml has no [project] version"
    return match.group(1)


def test_package_version_matches_pyproject():
    assert desktop_harness.__version__ == _pyproject_version()


def test_requires_python_boundary_matches_runtime():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=' in text
    assert sys.version_info >= (3, 10)


def test_skill_file_still_ships_as_package_data():
    packaged = SRC / "desktop_harness" / "data" / "SKILL.md"
    assert packaged.is_file(), "SKILL.md must stay packaged (wheel force-include target)"
    assert packaged.read_text(encoding="utf-8").strip(), "packaged SKILL.md is empty"


def test_root_skill_frontmatter_names_the_skill():
    text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    frontmatter = text.split("---", 2)[1]
    assert re.search(
        r"^name:\s*['\"]?desktop-harness['\"]?\s*$", frontmatter, flags=re.MULTILINE
    )


def test_gitignore_covers_local_artifacts():
    lines = {
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    for needed in (".venv/", "__pycache__/", ".pytest_cache/"):
        assert needed in lines


_SECRET_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bxai-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


@pytest.mark.parametrize("directory", ["src", "scripts"])
def test_no_credential_shaped_strings_in_shipped_code(directory):
    root = REPO_ROOT / directory
    if not root.is_dir():
        pytest.skip(f"{directory}/ not present")
    hits = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in {".png", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _SECRET_SHAPES:
            if pattern.search(text):
                hits.append(f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}")
    assert hits == []
