from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_harness import safety


class SafetyEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        os.environ.pop("DH_ALLOW_SENSITIVE", None)
        os.environ.pop("DH_SAFE", None)

    def test_allow_sensitive_accepts_only_explicit_truthy_values(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "YES"):
            with self.subTest(value=value):
                os.environ["DH_ALLOW_SENSITIVE"] = value
                self.assertTrue(safety.allow_sensitive())

        for value in ("", "0", "false", "no", "on", "unexpected"):
            with self.subTest(value=value):
                os.environ["DH_ALLOW_SENSITIVE"] = value
                self.assertFalse(safety.allow_sensitive())

    def test_safe_mode_defaults_on_and_can_be_disabled(self) -> None:
        self.assertTrue(safety.safe_mode())

        for value in ("0", "false", "no"):
            with self.subTest(value=value):
                os.environ["DH_SAFE"] = value
                self.assertFalse(safety.safe_mode())

        for value in ("1", "true", "yes"):
            with self.subTest(value=value):
                os.environ["DH_SAFE"] = value
                self.assertTrue(safety.safe_mode())

    def test_sensitive_name_is_blocked_case_insensitively(self) -> None:
        with self.assertRaises(PermissionError) as caught:
            safety.check_app_allowed("KEYCHAIN Access")

        self.assertIn("KEYCHAIN Access", str(caught.exception))

    def test_sensitive_bundle_is_blocked_even_when_name_is_generic(self) -> None:
        with self.assertRaises(PermissionError) as caught:
            safety.check_app_allowed(
                "FAKE_VALUE_FOR_TEST",
                "com.example.1password",
            )

        self.assertIn("com.example.1password", str(caught.exception))

    def test_allow_sensitive_override_allows_checked_app(self) -> None:
        os.environ["DH_ALLOW_SENSITIVE"] = "yes"

        safety.check_app_allowed("1Password")
        safety.check_app_allowed(
            "FAKE_VALUE_FOR_TEST",
            "com.example.1password",
        )

    def _check_frontmost(self, callback) -> None:
        package = importlib.import_module("desktop_harness")
        fake_windows = types.ModuleType("desktop_harness.windows")
        fake_windows.frontmost_app = callback

        module_patcher = mock.patch.dict(
            sys.modules,
            {"desktop_harness.windows": fake_windows},
        )
        module_patcher.start()
        self.addCleanup(module_patcher.stop)

        had_windows = hasattr(package, "windows")
        old_windows = getattr(package, "windows", None)
        package.windows = fake_windows
        try:
            safety.check_frontmost_allowed()
        finally:
            if had_windows:
                package.windows = old_windows
            else:
                delattr(package, "windows")

    def test_frontmost_sensitive_app_is_blocked(self) -> None:
        with self.assertRaises(PermissionError) as caught:
            self._check_frontmost(
                lambda: {
                    "name": "1Password",
                    "bundle_id": "com.example.1password",
                }
            )

        self.assertIn("1Password", str(caught.exception))

    def test_frontmost_benign_or_missing_app_is_allowed(self) -> None:
        self._check_frontmost(
            lambda: {
                "name": "FAKE_VALUE_FOR_TEST",
                "bundle_id": "com.example.fake",
            }
        )
        self._check_frontmost(lambda: None)

    def test_frontmost_lookup_failure_fails_open(self) -> None:
        def unavailable():
            raise RuntimeError("frontmost lookup unavailable")

        self._check_frontmost(unavailable)

    def test_safe_mode_blocks_only_reserved_helper_names(self) -> None:
        os.environ["DH_SAFE"] = "1"
        for name in ("run_shell", "shell", "osascript_raw"):
            with self.subTest(name=name):
                with self.assertRaises(PermissionError):
                    safety.check_helper_allowed(name)

        safety.check_helper_allowed("FAKE_VALUE_FOR_TEST")

        os.environ["DH_SAFE"] = "0"
        for name in ("run_shell", "shell", "osascript_raw"):
            with self.subTest(name=name, safe_mode="off"):
                safety.check_helper_allowed(name)

    def test_audit_writes_one_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            with mock.patch.object(safety, "_AUDIT", audit_path):
                safety.audit("fmb_edge_event", {"count": 1})

            lines = audit_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["event"], "fmb_edge_event")
            self.assertEqual(row["detail"], {"count": 1})
            self.assertIsInstance(row["ts"], (int, float))

    def test_audit_write_failure_is_swallowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(safety, "_AUDIT", Path(temp_dir)):
                safety.audit("fmb_edge_event", {"count": 1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
