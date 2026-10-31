"""回歸測試：敏感程式安全閘門與截圖路徑隔離。"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_harness import safety


_MISSING = object()


@contextmanager
def _capture_with_stubs(tmp_path: Path):
    """載入 capture.py，但不要求測試機器安裝 pyobjc 或存取真實桌面。"""
    package = importlib.import_module("desktop_harness")
    module_names = (
        "Quartz",
        "AppKit",
        "desktop_harness.capture",
        "desktop_harness.windows",
    )
    old_modules = {
        name: sys.modules.get(name, _MISSING)
        for name in module_names
    }
    old_attrs = {
        name: getattr(package, name, _MISSING)
        for name in ("capture", "windows")
    }

    quartz_calls: list[tuple[object, ...]] = []

    quartz = types.ModuleType("Quartz")
    quartz.CGRectNull = object()
    quartz.kCGWindowListOptionIncludingWindow = 1
    quartz.kCGWindowListOptionOnScreenOnly = 2
    quartz.kCGWindowImageBoundsIgnoreFraming = 4
    quartz.kCGWindowImageNominalResolution = 8
    quartz.kCGNullWindowID = 0

    def create_image(*args):
        quartz_calls.append(args)
        return object()

    quartz.CGWindowListCreateImage = create_image
    quartz.CGDisplayBounds = lambda *_args: object()
    quartz.CGMainDisplayID = lambda: 0

    class _BitmapImageRep:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithCGImage_(self, image):
            self.image = image
            return self

        def representationUsingType_properties_(self, *_args):
            return b"FAKE_PNG_DATA"

    appkit = types.ModuleType("AppKit")
    appkit.NSBitmapImageRep = _BitmapImageRep
    appkit.NSImage = object

    fake_windows = types.ModuleType("desktop_harness.windows")
    fake_windows.list_windows = lambda: []
    fake_windows.frontmost_app = lambda: None

    sys.modules["Quartz"] = quartz
    sys.modules["AppKit"] = appkit
    sys.modules["desktop_harness.windows"] = fake_windows
    for attr in ("capture", "windows"):
        if hasattr(package, attr):
            delattr(package, attr)
    setattr(package, "windows", fake_windows)
    sys.modules.pop("desktop_harness.capture", None)

    try:
        capture = importlib.import_module("desktop_harness.capture")
        yield capture, quartz_calls
    finally:
        sys.modules.pop("desktop_harness.capture", None)
        for name, old in old_modules.items():
            if old is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        for attr, old in old_attrs.items():
            if old is _MISSING:
                if hasattr(package, attr):
                    delattr(package, attr)
            else:
                setattr(package, attr, old)


class CaptureRegressionTests(unittest.TestCase):
    def test_default_capture_paths_are_unique_and_do_not_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with _capture_with_stubs(tmp_path) as (capture, quartz_calls):
                capture.TMP = tmp_path / "captures"
                capture.TMP.mkdir()
                audit_path = tmp_path / "audit.jsonl"

                with mock.patch.object(
                    safety, "_AUDIT", audit_path
                ), mock.patch.object(
                    capture.time, "time_ns", side_effect=[101, 202]
                ):
                    first = Path(capture.screenshot())
                    second = Path(capture.screenshot())

                self.assertNotEqual(first, second)
                self.assertTrue(first.is_file())
                self.assertTrue(second.is_file())
                self.assertEqual(first.read_bytes(), b"FAKE_PNG_DATA")
                self.assertEqual(second.read_bytes(), b"FAKE_PNG_DATA")
                self.assertEqual(len(quartz_calls), 2)
                self.assertEqual(len(audit_path.read_text().splitlines()), 2)

    def test_sensitive_target_is_blocked_before_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with _capture_with_stubs(tmp_path) as (capture, quartz_calls):
                with mock.patch.dict(
                    os.environ,
                    {"DH_ALLOW_SENSITIVE": "", "DH_SAFE": "1"},
                ):
                    with self.assertRaises(PermissionError):
                        capture.screenshot(app="1Password")
                self.assertEqual(quartz_calls, [])


class SafetyRegressionTests(unittest.TestCase):
    def test_sensitive_name_and_bundle_are_blocked(self):
        with mock.patch.dict(
            os.environ,
            {"DH_ALLOW_SENSITIVE": "", "DH_SAFE": "1"},
        ):
            with self.assertRaises(PermissionError):
                safety.check_app_allowed("1Password")
            with self.assertRaises(PermissionError):
                safety.check_app_allowed("Keychain Access")
            with self.assertRaises(PermissionError):
                safety.check_app_allowed("", "com.vendor.lastpass.extension")
            with self.assertRaises(PermissionError):
                safety.check_app_allowed("", "com.apple.keychainaccess")

            safety.check_app_allowed("TextEdit", "com.apple.TextEdit")

    def test_allow_sensitive_override(self):
        with mock.patch.dict(
            os.environ,
            {"DH_ALLOW_SENSITIVE": "1", "DH_SAFE": "1"},
        ):
            safety.check_app_allowed("1Password", "com.1password.1password")

    def test_safe_mode_blocks_high_risk_helper_names(self):
        blocked = ("run_shell", "shell", "osascript_raw")
        with mock.patch.dict(
            os.environ,
            {"DH_ALLOW_SENSITIVE": "", "DH_SAFE": "1"},
        ):
            for name in blocked:
                with self.subTest(name=name):
                    with self.assertRaises(PermissionError):
                        safety.check_helper_allowed(name)

        with mock.patch.dict(
            os.environ,
            {"DH_ALLOW_SENSITIVE": "", "DH_SAFE": "0"},
        ):
            for name in blocked:
                with self.subTest(name=name):
                    safety.check_helper_allowed(name)

    def test_frontmost_sensitive_app_is_blocked(self):
        package = importlib.import_module("desktop_harness")
        fake_windows = types.ModuleType("desktop_harness.windows")
        fake_windows.frontmost_app = lambda: {
            "name": "1Password",
            "bundle_id": "com.1password.1password",
            "pid": 1234,
        }

        with mock.patch.dict(
            sys.modules, {"desktop_harness.windows": fake_windows}
        ):
            with mock.patch.object(
                package, "windows", fake_windows, create=True
            ):
                with mock.patch.dict(
                    os.environ,
                    {"DH_ALLOW_SENSITIVE": "", "DH_SAFE": "1"},
                ):
                    with self.assertRaises(PermissionError):
                        safety.check_frontmost_allowed()

                    fake_windows.frontmost_app = lambda: {
                        "name": "TextEdit",
                        "bundle_id": "com.apple.TextEdit",
                        "pid": 1234,
                    }
                    safety.check_frontmost_allowed()


if __name__ == "__main__":
    unittest.main()
