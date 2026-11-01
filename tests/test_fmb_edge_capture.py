"""Edge-case and error-path tests for ``desktop_harness.capture`` (fmb edge suite).

The module is only reachable on hosts with pyobjc installed; otherwise the whole
file is skipped. No real display is ever captured: ``capture.Quartz`` and
``capture.NSBitmapImageRep`` are replaced with recorders/fakes before each call,
and every call passes an explicit path inside ``tmp_path`` (except the one test
that intentionally exercises the default unique filename, which cleans up).
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:  # pyobjc is a runtime dependency, not a test dependency
    from desktop_harness import capture, safety
except Exception as exc:  # pragma: no cover - depends on host
    pytest.skip(f"capture module needs pyobjc (Quartz/AppKit): {exc}", allow_module_level=True)

PNG_BYTES = b"\x89PNG\r\n\x1a\nFAKE_PNG_FOR_TEST"


@pytest.fixture(autouse=True)
def isolated_audit(tmp_path, monkeypatch):
    """Route capture's audit writes into tmp_path, never ~/.desktop-harness."""
    log_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(safety, "_AUDIT", log_path)
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    return log_path


class FakeQuartz:
    """Records CG calls instead of asking the window server for pixels."""

    kCGWindowListOptionIncludingWindow = 8
    kCGWindowImageBoundsIgnoreFraming = 1
    kCGWindowImageNominalResolution = 32
    kCGWindowListOptionOnScreenOnly = 16
    kCGNullWindowID = 0
    CGRectNull = ("CGRectNull",)

    def __init__(self):
        self.calls = []

    def CGDisplayBounds(self, display_id):
        self.calls.append(("CGDisplayBounds", display_id))
        return ("display-bounds", display_id)

    def CGMainDisplayID(self):
        self.calls.append(("CGMainDisplayID",))
        return 1

    def CGWindowListCreateImage(self, rect, option, window_id, image_option):
        self.calls.append(
            ("CGWindowListCreateImage", rect, option, window_id, image_option)
        )
        return ("fake-image", window_id)


def _fake_bitmap_rep(monkeypatch, payload=PNG_BYTES):
    class Rep:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithCGImage_(self, _image):
            return self

        def representationUsingType_properties_(self, _file_type, _props):
            return payload

    monkeypatch.setattr(capture, "NSBitmapImageRep", Rep)
    return Rep


def _fake_windows(monkeypatch, windows):
    monkeypatch.setattr(
        capture, "winmod", types.SimpleNamespace(list_windows=lambda: list(windows))
    )


# ---------------------------------------------------------------------------
# _save_cgimage boundaries
# ---------------------------------------------------------------------------

def test_save_cgimage_rejects_missing_image(tmp_path):
    target = tmp_path / "shot.png"
    with pytest.raises(RuntimeError) as excinfo:
        capture._save_cgimage(None, target)
    assert "no image" in str(excinfo.value)
    assert not target.exists()


def test_save_cgimage_reports_encoder_failure(tmp_path, monkeypatch):
    _fake_bitmap_rep(monkeypatch, payload=None)
    target = tmp_path / "shot.png"
    with pytest.raises(RuntimeError) as excinfo:
        capture._save_cgimage("fake-image", target)
    assert "encode" in str(excinfo.value)
    assert not target.exists()


def test_save_cgimage_writes_payload_and_returns_path(tmp_path, monkeypatch):
    _fake_bitmap_rep(monkeypatch)
    target = tmp_path / "shot.png"
    result = capture._save_cgimage("fake-image", target)
    assert Path(result) == target
    assert target.read_bytes() == PNG_BYTES


def test_save_cgimage_accepts_a_str_path(tmp_path, monkeypatch):
    _fake_bitmap_rep(monkeypatch)
    target = tmp_path / "shot.png"
    result = capture._save_cgimage("fake-image", str(target))
    assert isinstance(result, Path)
    assert result == target
    assert target.read_bytes() == PNG_BYTES


# ---------------------------------------------------------------------------
# screenshot(): gate ordering and window resolution
# ---------------------------------------------------------------------------

def test_screenshot_blocks_sensitive_app_before_touching_quartz(tmp_path, monkeypatch):
    touched = []

    class ExplodingQuartz:
        def __getattr__(self, name):
            touched.append(name)
            raise AssertionError(f"Quartz.{name} must not be reached")

    monkeypatch.setattr(capture, "Quartz", ExplodingQuartz())
    target = tmp_path / "shot.png"
    with pytest.raises(PermissionError):
        capture.screenshot(app="1Password", path=target)
    assert touched == []
    assert not target.exists()


def test_screenshot_unknown_app_raises_and_writes_nothing(tmp_path, monkeypatch):
    _fake_windows(monkeypatch, [])
    target = tmp_path / "shot.png"
    with pytest.raises(RuntimeError) as excinfo:
        capture.screenshot(app="NoSuchApp", path=target)
    assert "no on-screen window" in str(excinfo.value)
    assert not target.exists()


def test_screenshot_matches_window_by_title_case_insensitively(tmp_path, monkeypatch):
    quartz = FakeQuartz()
    monkeypatch.setattr(capture, "Quartz", quartz)
    _fake_bitmap_rep(monkeypatch)
    _fake_windows(
        monkeypatch,
        [{"id": 42, "app": "Safari", "title": "Example Domain", "x": 0, "y": 0, "w": 1, "h": 1}],
    )
    target = tmp_path / "shot.png"
    result = capture.screenshot(app="example domain", path=target)
    assert result == str(target)
    window_calls = [c for c in quartz.calls if c[0] == "CGWindowListCreateImage"]
    assert window_calls, "expected a window-scoped capture"
    assert window_calls[0][3] == 42


def test_screenshot_window_with_none_title_does_not_crash(tmp_path, monkeypatch):
    quartz = FakeQuartz()
    monkeypatch.setattr(capture, "Quartz", quartz)
    _fake_bitmap_rep(monkeypatch)
    _fake_windows(monkeypatch, [{"id": 7, "app": "Notes", "title": None}])
    target = tmp_path / "shot.png"
    capture.screenshot(app="Notes", path=target)
    window_calls = [c for c in quartz.calls if c[0] == "CGWindowListCreateImage"]
    assert window_calls[0][3] == 7


def test_screenshot_without_app_runs_the_frontmost_gate(tmp_path, monkeypatch):
    gate_calls = []
    monkeypatch.setattr(safety, "check_frontmost_allowed", lambda: gate_calls.append("gate"))
    quartz = FakeQuartz()
    monkeypatch.setattr(capture, "Quartz", quartz)
    _fake_bitmap_rep(monkeypatch)
    target = tmp_path / "shot.png"
    capture.screenshot(window_id=7, path=target)
    assert gate_calls == ["gate"]
    window_calls = [c for c in quartz.calls if c[0] == "CGWindowListCreateImage"]
    assert window_calls[0][3] == 7


def test_screenshot_full_display_uses_main_display_and_audits(
    tmp_path, monkeypatch, isolated_audit
):
    monkeypatch.setattr(safety, "check_frontmost_allowed", lambda: None)
    quartz = FakeQuartz()
    monkeypatch.setattr(capture, "Quartz", quartz)
    _fake_bitmap_rep(monkeypatch)
    target = tmp_path / "shot.png"
    result = capture.screenshot(path=target)
    assert result == str(target)
    assert target.read_bytes() == PNG_BYTES
    names = [call[0] for call in quartz.calls]
    assert "CGMainDisplayID" in names
    assert "CGDisplayBounds" in names
    window_calls = [c for c in quartz.calls if c[0] == "CGWindowListCreateImage"]
    assert window_calls[0][3] == FakeQuartz.kCGNullWindowID
    rows = [
        json.loads(line)
        for line in isolated_audit.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["event"] == "screenshot"
    assert rows[-1]["detail"]["app"] is None
    assert rows[-1]["detail"]["window_id"] is None
    assert rows[-1]["detail"]["path"] == str(target)


def test_screenshot_does_not_create_missing_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(safety, "check_frontmost_allowed", lambda: None)
    monkeypatch.setattr(capture, "Quartz", FakeQuartz())
    _fake_bitmap_rep(monkeypatch)
    target = tmp_path / "missing-dir" / "shot.png"
    with pytest.raises(FileNotFoundError):
        capture.screenshot(window_id=3, path=target)
    assert not target.exists()


def test_default_capture_paths_are_unique_and_inside_capture_tmp(monkeypatch):
    monkeypatch.setattr(safety, "check_frontmost_allowed", lambda: None)
    monkeypatch.setattr(capture, "Quartz", FakeQuartz())
    _fake_bitmap_rep(monkeypatch)
    first = Path(capture.screenshot(window_id=1))
    second = Path(capture.screenshot(window_id=1))
    try:
        assert first.parent == capture.TMP
        assert second.parent == capture.TMP
        assert first != second
        assert first.name.startswith(f"capture-{os.getpid()}-")
        assert first.is_file() and second.is_file()
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# window_info boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("windows", "app", "expected_id"),
    [
        ([], None, None),
        ([], "Safari", None),
        ([{"id": 1, "app": "Safari", "title": "a"}], None, 1),
        ([{"id": 1, "app": "Safari", "title": "a"}], "safari", 1),
        ([{"id": 1, "app": "Safari", "title": "a"}], "Notes", None),
    ],
)
def test_window_info_boundaries(monkeypatch, windows, app, expected_id):
    _fake_windows(monkeypatch, windows)
    info = capture.window_info(app)
    if expected_id is None:
        assert info is None
    else:
        assert info["id"] == expected_id
