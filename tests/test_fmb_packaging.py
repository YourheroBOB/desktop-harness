"""Packaging / consistency regression tests.

Guards the release-hygiene issues called out in docs/PRE-RELEASE-REVIEW.md:
version alignment, packaged skill data, console-script entry point.
Pure file/text checks — no GUI, no network.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from desktop_harness import __version__  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_text() -> str:
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_version_matches_pyproject():
    m = re.search(r'^version\s*=\s*"([^"]+)"', _pyproject_text(), re.MULTILINE)
    assert m, "no project version found in pyproject.toml"
    assert m.group(1) == __version__, (
        f"pyproject version {m.group(1)!r} != __init__.__version__ {__version__!r}"
    )


def test_readme_status_matches_version():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"v{__version__}" in readme, "README status/version line is out of sync"


def test_packaged_skill_data_exists():
    skill = ROOT / "src" / "desktop_harness" / "data" / "SKILL.md"
    assert skill.is_file(), "src/desktop_harness/data/SKILL.md is missing"
    content = skill.read_text(encoding="utf-8")
    assert "desktop-harness" in content
    assert "## When to use" in content


def test_pyproject_force_includes_skill():
    text = _pyproject_text()
    assert "[tool.hatch.build.targets.wheel.force-include]" in text
    assert '"SKILL.md"' in text


def test_console_script_entry_point_declared():
    assert 'desktop-harness = "desktop_harness.run:main"' in _pyproject_text()


def test_run_module_exposes_main():
    try:
        run_mod = importlib.import_module("desktop_harness.run")
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"desktop_harness.run not importable here: {e}")
    assert hasattr(run_mod, "main")


def test_required_python_floor_declared():
    m = re.search(r'requires-python\s*=\s*">=\s*([\d.]+)"', _pyproject_text())
    assert m, "no requires-python floor in pyproject.toml"


def test_license_file_present():
    license_file = ROOT / "LICENSE"
    assert license_file.is_file()
    assert "MIT" in license_file.read_text(encoding="utf-8")
