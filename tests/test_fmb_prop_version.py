#!/usr/bin/env python3
"""Packaging invariants for desktop-harness (version single source of truth).

Prevents the historical critical issue in docs/PRE-RELEASE-REVIEW.md #3:
``__version__`` drifting from ``pyproject.toml``.

Run:

    python3 tests/test_fmb_prop_version.py -v
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from desktop_harness import __version__  # noqa: E402

PYPROJECT = REPO_ROOT / "pyproject.toml"


def _pyproject_version() -> str:
    """Parse the project version; tomllib on 3.11+, regex fallback on 3.10."""
    try:
        import tomllib  # Python 3.11+
        with PYPROJECT.open("rb") as f:
            data = tomllib.load(f)
        return data["project"]["version"]
    except ImportError:
        match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(), re.MULTILINE)
        if match is None:
            raise AssertionError("cannot parse version from pyproject.toml")
        return match.group(1)


class TestVersionInvariants(unittest.TestCase):
    def test_version_matches_pyproject(self):
        # Single source of truth: package version == declared project version.
        self.assertEqual(__version__, _pyproject_version())

    def test_version_format(self):
        # Shape invariant: plain dotted triple (no pre-release/build surprises
        # that release tooling / check-update comparisons don't handle).
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_skill_files_present(self):
        # Packaging invariant: the wheel force-include target must exist in the
        # tree (src/desktop_harness/data/SKILL.md) alongside the root SKILL.md
        # (see ADR-0002 — two copies must both exist to be kept in sync).
        self.assertTrue((REPO_ROOT / "SKILL.md").is_file(), "root SKILL.md missing")
        self.assertTrue(
            (REPO_ROOT / "src" / "desktop_harness" / "data" / "SKILL.md").is_file(),
            "packaged data/SKILL.md missing",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
