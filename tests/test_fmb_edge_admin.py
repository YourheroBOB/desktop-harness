"""Error-path tests for ``desktop_harness.admin.run_doctor`` (fmb edge suite).

Only the dependency-failure branches are exercised: each test makes one pyobjc
framework unimportable, which must short-circuit the doctor before it ever tries
to read the screen. No capture, no permissions prompt, no network.

Regression note: the first version of this file asserted that a *dependency*
failure also printed the two privacy-pane URLs. ``admin.run_doctor()`` returns
immediately from that branch (no permissions section), which is the correct
behaviour — there is nothing to grant while pyobjc is missing. The test was
corrected to document that boundary instead of demanding a hint the code
deliberately does not print; the product source is untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_harness import admin  # noqa: E402


@pytest.mark.parametrize("missing", ["Quartz", "AppKit", "ApplicationServices"])
def test_doctor_fails_cleanly_when_a_framework_is_missing(monkeypatch, capsys, missing):
    monkeypatch.setitem(sys.modules, missing, None)  # makes `import <missing>` raise ImportError
    rc = admin.run_doctor()
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("desktop-harness doctor")
    assert "[FAIL] pyobjc frameworks" in out
    assert "install deps in the project venv" in out
    assert "all clear" not in out
    # Exactly one failure is counted: the dependency check returns immediately.
    assert out.count("[FAIL]") == 1


def test_dependency_failure_does_not_blame_permissions(monkeypatch, capsys):
    """Missing pyobjc must not send the user to the privacy panes.

    Permissions are meaningless until the frameworks import, so the early
    return intentionally omits the ``open "x-apple.systempreferences:…"`` hints.
    """
    monkeypatch.setitem(sys.modules, "Quartz", None)
    assert admin.run_doctor() == 1
    out = capsys.readouterr().out
    assert "Privacy_Accessibility" not in out
    assert "Privacy_ScreenCapture" not in out
    assert "install deps in the project venv" in out


def test_permission_pane_hints_are_still_present_in_the_module():
    """Guard against the remediation hints being deleted outright.

    The panes are printed on the *runtime* failure path, which would need a
    real AX/capture stack; asserting on the source keeps this cheap and
    host-independent.
    """
    source = Path(admin.__file__).read_text(encoding="utf-8")
    assert "Privacy_Accessibility" in source
    assert "Privacy_ScreenCapture" in source
    assert "fully quit and restart" in source
    assert "AXIsProcessTrusted" in source


def test_doctor_short_circuits_before_any_capture(monkeypatch, capsys):
    capture = pytest.importorskip("desktop_harness.capture")
    calls = []
    monkeypatch.setattr(
        capture, "screenshot", lambda *a, **k: calls.append((a, k)) or "unused.png"
    )
    monkeypatch.setitem(sys.modules, "Quartz", None)
    assert admin.run_doctor() == 1
    assert calls == []
    capsys.readouterr()
