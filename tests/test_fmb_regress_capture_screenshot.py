"""回歸測試：capture.screenshot 的閘門與檔名唯一化。

對應的修復痕跡：
  * review #17 / ADR-0009 —— 預設截圖路徑不可共用（早期是單一
    capture.png，並發步驟互相覆蓋），現為 capture-<pid>-<time_ns>.png；
  * ADR-0008 —— 截圖與點擊同級：指定 app 時走名稱 gate，未指定 app
    時走前景 gate（「拍下畫面上的密碼」等級的洩漏）；
  * 防禦性檢查：CGImage 為 None 或 PNG 編碼失敗時必須丟 RuntimeError，
    不可回傳半殘路徑；
  * 成功截圖要寫 audit（event="screenshot"）。

作法：把假 Quartz / AppKit / windows 注入 sys.modules 後才 import capture，
因此不需要 pyobjc、不開視窗、不連網路；所有輸出檔落在 tmp_path。
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import desktop_harness  # noqa: E402
from desktop_harness import safety  # noqa: E402


class _FakeBitmapRep:
    def __init__(self, data):
        self._data = data

    def representationUsingType_properties_(self, filetype, properties):
        return self._data


class _FakeBitmapAlloc:
    def __init__(self, data):
        self._data = data

    def initWithCGImage_(self, image):
        return _FakeBitmapRep(self._data)


class _Fakes:
    """所有假模組共用的可調狀態。"""

    def __init__(self):
        self.png_bytes = b"\x89PNG\r\n\x1a\nFAKE_PNG_FOR_TEST"
        self.image = object()
        self.windows = []
        self.frontmost = None
        self.capture_calls = []
        self.const_including_window = 1
        self.const_on_screen_only = 2
        self.const_bounds_ignore_framing = 4
        self.const_nominal_resolution = 8
        self.const_null_window = 0

    def quartz_module(self):
        fakes = self
        mod = types.ModuleType("Quartz")
        mod.CGRectNull = "CGRectNull"
        mod.kCGWindowListOptionIncludingWindow = fakes.const_including_window
        mod.kCGWindowListOptionOnScreenOnly = fakes.const_on_screen_only
        mod.kCGWindowImageBoundsIgnoreFraming = fakes.const_bounds_ignore_framing
        mod.kCGWindowImageNominalResolution = fakes.const_nominal_resolution
        mod.kCGNullWindowID = fakes.const_null_window

        def _create_image(rect, option, wid, image_option):
            fakes.capture_calls.append(
                {
                    "rect": rect,
                    "option": option,
                    "wid": wid,
                    "image_option": image_option,
                }
            )
            return fakes.image

        mod.CGWindowListCreateImage = _create_image
        mod.CGMainDisplayID = lambda: 1
        mod.CGDisplayBounds = lambda display: "main-display-bounds"
        return mod

    def appkit_module(self):
        fakes = self
        mod = types.ModuleType("AppKit")

        class NSBitmapImageRep:
            @staticmethod
            def alloc():
                return _FakeBitmapAlloc(fakes.png_bytes)

        mod.NSBitmapImageRep = NSBitmapImageRep
        mod.NSImage = object
        return mod

    def windows_module(self):
        fakes = self
        mod = types.ModuleType("desktop_harness.windows")
        mod.list_windows = lambda: list(fakes.windows)
        mod.frontmost_app = lambda: fakes.frontmost
        return mod


@pytest.fixture()
def cap(monkeypatch, tmp_path):
    fakes = _Fakes()
    fakes.out_dir = tmp_path
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    monkeypatch.setattr(safety, "_AUDIT", tmp_path / "audit.jsonl")

    fake_windows = fakes.windows_module()
    monkeypatch.setitem(sys.modules, "Quartz", fakes.quartz_module())
    monkeypatch.setitem(sys.modules, "AppKit", fakes.appkit_module())
    monkeypatch.setitem(sys.modules, "desktop_harness.windows", fake_windows)
    monkeypatch.setattr(desktop_harness, "windows", fake_windows, raising=False)

    sys.modules.pop("desktop_harness.capture", None)
    module = importlib.import_module("desktop_harness.capture")
    monkeypatch.setattr(module, "TMP", tmp_path)
    try:
        yield module, fakes
    finally:
        sys.modules.pop("desktop_harness.capture", None)
        try:
            delattr(desktop_harness, "capture")
        except AttributeError:
            pass


# --------------------------------------------------------------------------
# 預設路徑唯一化（review #17）
# --------------------------------------------------------------------------
def test_default_capture_path_is_unique_per_call(cap):
    module, fakes = cap
    first = module.screenshot(window_id=42)
    second = module.screenshot(window_id=42)

    assert first != second
    expected = re.compile(rf"^capture-{os.getpid()}-\d+\.png$")
    for out in (first, second):
        path = Path(out)
        assert path.parent == fakes.out_dir
        assert expected.match(path.name), path.name
        assert path.exists()
        assert path.read_bytes() == fakes.png_bytes


def test_explicit_path_is_respected(cap):
    module, fakes = cap
    target = fakes.out_dir / "explicit.png"
    out = module.screenshot(window_id=7, path=target)
    assert Path(out) == target
    assert target.read_bytes() == fakes.png_bytes


# --------------------------------------------------------------------------
# 敏感 app / 前景閘門（ADR-0008）
# --------------------------------------------------------------------------
def test_app_name_gate_blocks_sensitive_app_before_capture(cap):
    module, fakes = cap
    with pytest.raises(PermissionError) as exc:
        module.screenshot(app="1Password")
    assert "DH_ALLOW_SENSITIVE" in str(exc.value)
    assert fakes.capture_calls == []
    assert list(fakes.out_dir.glob("*.png")) == []


def test_unscoped_capture_blocked_when_sensitive_app_frontmost(cap):
    module, fakes = cap
    fakes.frontmost = {"name": "Bitwarden", "bundle_id": "com.bitwarden.desktop"}
    with pytest.raises(PermissionError):
        module.screenshot()
    assert fakes.capture_calls == []
    assert list(fakes.out_dir.glob("*.png")) == []


def test_unscoped_capture_allowed_when_ordinary_app_frontmost(cap):
    module, fakes = cap
    fakes.frontmost = {"name": "Finder", "bundle_id": "com.apple.finder"}
    out = module.screenshot()
    assert Path(out).exists()
    last = fakes.capture_calls[-1]
    assert last["option"] == fakes.const_on_screen_only
    assert last["wid"] == fakes.const_null_window


def test_sensitive_app_allowed_with_escape_hatch(cap, monkeypatch):
    module, fakes = cap
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    out = module.screenshot(app="1Password", window_id=9)
    assert Path(out).exists()
    last = fakes.capture_calls[-1]
    assert last["option"] == fakes.const_including_window
    assert last["wid"] == 9


# --------------------------------------------------------------------------
# app → window 對應
# --------------------------------------------------------------------------
def test_app_lookup_uses_window_list(cap):
    module, fakes = cap
    fakes.windows = [
        {"app": "Finder", "title": "Desktop", "id": 1},
        {"app": "TextEdit", "title": "notes.txt", "id": 22},
    ]
    out = module.screenshot(app="TextEdit")
    assert Path(out).exists()
    assert fakes.capture_calls[-1]["wid"] == 22


def test_app_lookup_can_match_window_title(cap):
    module, fakes = cap
    fakes.windows = [{"app": "Safari", "title": "TextEdit basics", "id": 33}]
    out = module.screenshot(app="TextEdit")
    assert Path(out).exists()
    assert fakes.capture_calls[-1]["wid"] == 33


def test_unknown_app_raises(cap):
    module, fakes = cap
    fakes.windows = []
    with pytest.raises(RuntimeError) as exc:
        module.screenshot(app="NotRunningAnywhere")
    assert "no on-screen window" in str(exc.value)
    assert fakes.capture_calls == []


# --------------------------------------------------------------------------
# 防禦性檢查與 audit
# --------------------------------------------------------------------------
def test_missing_image_raises(cap):
    module, fakes = cap
    fakes.image = None
    with pytest.raises(RuntimeError) as exc:
        module.screenshot(window_id=5)
    assert "no image" in str(exc.value)


def test_png_encoding_failure_raises(cap):
    module, fakes = cap
    fakes.png_bytes = None
    with pytest.raises(RuntimeError) as exc:
        module.screenshot(window_id=5)
    assert "PNG" in str(exc.value)


def test_successful_screenshot_is_audited(cap):
    module, fakes = cap
    out = module.screenshot(window_id=5)
    log = fakes.out_dir / "audit.jsonl"
    assert log.exists()
    rows = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[-1]["event"] == "screenshot"
    assert rows[-1]["detail"]["window_id"] == 5
    assert rows[-1]["detail"]["path"] == out
