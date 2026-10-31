"""Contract tests for the public surface of desktop_harness.safety.

Locks current external behaviour:
  - allow_sensitive() / safe_mode() env semantics
  - check_app_allowed(): PermissionError on sensitive names/bundles, message shape
  - check_helper_allowed(): blocked helper names, safe-mode gating
  - audit(): JSONL row shape (ts/event/detail), append semantics, error swallowing
  - CONFIRM_GUIDANCE: non-empty guidance string

Pure stdlib — no pyobjc, no GUI, no network. Uses only tmp dirs for writes.
Runnable via `python -m unittest discover -s tests` or pytest.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_ENV_KEYS = ("DH_ALLOW_SENSITIVE", "DH_SAFE", "DH_AUDIT_LOG")


class SafetyContractTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        os.environ["DH_AUDIT_LOG"] = str(Path(self._tmp.name) / "audit.jsonl")
        import desktop_harness.safety as safety
        self.safety = importlib.reload(safety)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()
        import desktop_harness.safety as safety
        importlib.reload(safety)

    # --- allow_sensitive() ---------------------------------------------

    def test_allow_sensitive_default_off_and_falsy_values(self):
        for v in ("", "0", "no", "off", "random"):
            os.environ["DH_ALLOW_SENSITIVE"] = v
            self.assertFalse(self.safety.allow_sensitive(), v)

    def test_allow_sensitive_truthy_values_case_insensitive(self):
        for v in ("1", "true", "yes", "TRUE", "Yes", "True"):
            os.environ["DH_ALLOW_SENSITIVE"] = v
            self.assertTrue(self.safety.allow_sensitive(), v)

    # --- safe_mode() ----------------------------------------------------

    def test_safe_mode_default_on(self):
        os.environ.pop("DH_SAFE", None)
        self.assertTrue(self.safety.safe_mode())

    def test_safe_mode_off_values(self):
        for v in ("0", "false", "no"):
            os.environ["DH_SAFE"] = v
            self.assertFalse(self.safety.safe_mode(), v)

    def test_safe_mode_on_values(self):
        for v in ("1", "true", "yes"):
            os.environ["DH_SAFE"] = v
            self.assertTrue(self.safety.safe_mode(), v)

    # --- check_app_allowed() --------------------------------------------

    def test_check_app_allowed_normal_apps_pass_and_return_none(self):
        for name in ("TextEdit", "Safari", "Finder"):
            self.assertIsNone(self.safety.check_app_allowed(name), name)

    def test_check_app_allowed_blocks_sensitive_names(self):
        for name in ("1Password", "Bitwarden", "Keychain Access",
                     "LastPass", "KeePassXC", "Dashlane", "NordPass",
                     "Enpass", "Apple Wallet", "My Bank App"):
            with self.assertRaises(PermissionError, msg=name) as cm:
                self.safety.check_app_allowed(name)
            self.assertIn("DH_ALLOW_SENSITIVE", str(cm.exception))
            self.assertIn(name, str(cm.exception))

    def test_check_app_allowed_blocks_sensitive_bundle_ids(self):
        for bundle in ("com.agilebits.1password", "eu.bitwarden.desktop"):
            with self.assertRaises(PermissionError, msg=bundle):
                self.safety.check_app_allowed("Whatever", bundle)
        # non-sensitive bundle passes
        self.assertIsNone(
            self.safety.check_app_allowed("Safari", "com.apple.Safari"))

    def test_check_app_allowed_env_override_unblocks(self):
        os.environ["DH_ALLOW_SENSITIVE"] = "1"
        self.assertIsNone(self.safety.check_app_allowed("1Password"))

    # --- check_helper_allowed() ------------------------------------------

    def test_check_helper_allowed_blocks_high_risk_names_in_safe_mode(self):
        for name in ("run_shell", "shell", "osascript_raw"):
            with self.assertRaises(PermissionError, msg=name) as cm:
                self.safety.check_helper_allowed(name)
            self.assertIn("safe mode", str(cm.exception))

    def test_check_helper_allowed_normal_helpers_never_raise(self):
        for name in ("click_text", "type_text", "open_app", "labels"):
            self.assertIsNone(self.safety.check_helper_allowed(name), name)

    def test_check_helper_allowed_disabled_when_safe_mode_off(self):
        os.environ["DH_SAFE"] = "0"
        self.assertIsNone(self.safety.check_helper_allowed("run_shell"))

    # --- check_frontmost_allowed() ---------------------------------------

    def test_check_frontmost_allowed_never_raises_with_override(self):
        os.environ["DH_ALLOW_SENSITIVE"] = "1"
        self.assertIsNone(self.safety.check_frontmost_allowed())

    # --- audit() ---------------------------------------------------------

    def test_audit_appends_jsonl_rows_with_contract_shape(self):
        log = Path(self._tmp.name) / "audit.jsonl"
        self.safety.audit("screenshot", {"app": "TextEdit", "path": "/tmp/x"})
        self.assertTrue(log.exists())
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row), {"ts", "event", "detail"})
        self.assertIsInstance(row["ts"], float)
        self.assertEqual(row["event"], "screenshot")
        self.assertEqual(row["detail"], {"app": "TextEdit", "path": "/tmp/x"})
        # second call appends
        self.safety.audit("activate", None)
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["event"], "activate")
        self.assertEqual(rows[1]["detail"], {})

    def test_audit_swallows_write_errors(self):
        blocker = Path(self._tmp.name) / "blocker"
        blocker.write_text("not a directory")
        os.environ["DH_AUDIT_LOG"] = str(blocker / "audit.jsonl")
        importlib.reload(self.safety)
        self.assertIsNone(self.safety.audit("screenshot", {"app": "x"}))

    # --- guidance ---------------------------------------------------------

    def test_confirm_guidance_is_nonempty_and_mentions_asking(self):
        g = self.safety.CONFIRM_GUIDANCE
        self.assertIsInstance(g, str)
        self.assertTrue(g.strip())
        self.assertIn("ask", g.lower())


if __name__ == "__main__":
    unittest.main()
