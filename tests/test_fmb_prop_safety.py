#!/usr/bin/env python3
"""Property / table-driven invariant tests for ``desktop_harness.safety``.

Scope: pure, env-driven logic only — no pyobjc, no GUI, no network, and no
writes outside ``tempfile`` sandboxes (the audit target is always patched
to a temp path, never the real ``~/.desktop-harness/audit.jsonl``).

Invariants covered
------------------
- ``_looks_sensitive``: case-insensitive substring detection on both the
  name and bundle channels; determinism; boundary (empty / whitespace);
  every bundle substring is also a name substring (design invariant).
- ``check_app_allowed``: exception-based gate is idempotent; benign names
  pass repeatedly; sensitive name OR bundle raises ``PermissionError`` with
  a remediation hint; ``DH_ALLOW_SENSITIVE`` override table.
- ``allow_sensitive`` / ``safe_mode``: full env-value tables including the
  default-when-unset and the no-whitespace-stripping boundary.
- ``check_helper_allowed``: exact-match blocklist; blocked only in safe mode
  without override; arbitrary non-blocked names never raise; idempotent.
- ``check_frontmost_allowed``: sensitive frontmost -> raise; benign / None /
  underlying ``frontmost_app()`` failure -> silent pass; override honored.
- ``audit``: append-only JSONL; per-line JSON roundtrip; non-decreasing ts;
  non-JSON-serializable detail never raises; unwritable path never raises.

Run (no third-party dependencies required):

    python3 tests/test_fmb_prop_safety.py -v

or, if pytest happens to be installed in the environment:

    python3 -m pytest tests/test_fmb_prop_safety.py -q
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

# Bootstrap import path to the repo's src/ (same trick as the ./desktop-harness
# dev launcher). Never touches anything outside the repo / temp dirs.
REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from desktop_harness import safety  # noqa: E402
import desktop_harness  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DH_KEYS = (
    "DH_ALLOW_SENSITIVE",
    "DH_SAFE",
    "DH_AUDIT_LOG",
    "DH_SOCKET",
    "DH_TOKEN_PATH",
    "DH_NO_DAEMON",
    "DH_PRESENCE",
    "DH_MOUSE_INSTANT",
)


@contextmanager
def dh_env(**kwargs):
    """Run with a scrubbed DH_* environment; restore exactly afterward.

    A value of ``None`` (or ``""``) means the variable is unset.
    """
    saved = {k: os.environ.get(k) for k in _DH_KEYS}
    for k in _DH_KEYS:
        os.environ.pop(k, None)
    for k, v in kwargs.items():
        if v is None or v == "":
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


_RAISE = object()  # sentinel: frontmost_app() itself raises


@contextmanager
def fake_windows_frontmost(frontmost):
    """Stub ``desktop_harness.windows`` so the frontmost gate needs no pyobjc."""
    mod = types.ModuleType("desktop_harness.windows")
    if frontmost is _RAISE:
        def frontmost_app():
            raise RuntimeError("simulated frontmost_app failure")
    else:
        def frontmost_app():
            return frontmost
    mod.frontmost_app = frontmost_app

    saved_mod = sys.modules.get("desktop_harness.windows")
    had_attr = hasattr(desktop_harness, "windows")
    saved_attr = getattr(desktop_harness, "windows", None)
    sys.modules["desktop_harness.windows"] = mod
    desktop_harness.windows = mod
    try:
        yield
    finally:
        if saved_mod is None:
            sys.modules.pop("desktop_harness.windows", None)
        else:
            sys.modules["desktop_harness.windows"] = saved_mod
        if had_attr:
            desktop_harness.windows = saved_attr
        elif hasattr(desktop_harness, "windows"):
            delattr(desktop_harness, "windows")


# ---------------------------------------------------------------------------
# _looks_sensitive — detection invariants
# ---------------------------------------------------------------------------

class TestLooksSensitive(unittest.TestCase):
    BENIGN = (
        "TextEdit", "Finder", "Safari", "Notes", "Xcode", "Terminal",
        "System Settings", "Music", "Preview", "Messages",
    )

    def test_every_name_substring_detected_case_insensitive(self):
        # Property: for every declared sensitive name substring s and every
        # casing c of s, any app name containing c is flagged.
        for s in safety._SENSITIVE_NAME_SUBSTR:
            for variant in (s, s.upper(), s.capitalize(), s.title()):
                self.assertTrue(
                    safety._looks_sensitive(f"MyApp {variant} Pro", ""),
                    msg=f"name substring {s!r} variant {variant!r} not detected",
                )

    def test_every_bundle_substring_detected_via_bundle_channel(self):
        # Property: the bundle channel detects its substrings even when the
        # display name is completely benign.
        for s in safety._SENSITIVE_BUNDLE_SUBSTR:
            self.assertTrue(
                safety._looks_sensitive("Totally Benign App", f"com.example.{s}.suite"),
                msg=f"bundle substring {s!r} not detected",
            )

    def test_benign_names_pass(self):
        for name in self.BENIGN:
            self.assertFalse(safety._looks_sensitive(name, "com.apple.benign"))

    def test_case_invariance_roundtrip(self):
        # Roundtrip-style invariant: detection(f(x)) == detection(x) for the
        # case transformations upper/lower/title.
        samples = ["1Password", "MyBankTool", "Bitwarden", "TextEdit", "Keychain Viewer"]
        for n in samples:
            base = safety._looks_sensitive(n, "")
            for transform in (str.upper, str.lower, str.title):
                self.assertEqual(
                    safety._looks_sensitive(transform(n), ""),
                    base,
                    msg=f"case transform {transform.__name__} changed verdict for {n!r}",
                )

    def test_boundary_empty_and_whitespace(self):
        # Boundary: no name, no bundle, or whitespace-only -> not sensitive.
        self.assertFalse(safety._looks_sensitive("", ""))
        self.assertFalse(safety._looks_sensitive("   ", "  "))

    def test_determinism_repeated_calls(self):
        # Purity/determinism: identical inputs always give identical verdicts.
        for name in ("1Password", "TextEdit", "Wallet App", "Safari"):
            first = safety._looks_sensitive(name, "")
            for _ in range(50):
                self.assertEqual(safety._looks_sensitive(name, ""), first)

    def test_bundle_substrings_subset_of_name_substrings(self):
        # Documented design invariant: anything gated via bundle id is also
        # gated via display name (name channel is the wider net).
        self.assertTrue(
            set(safety._SENSITIVE_BUNDLE_SUBSTR) <= set(safety._SENSITIVE_NAME_SUBSTR),
            msg="bundle-only substrings exist; name channel would miss them",
        )


# ---------------------------------------------------------------------------
# check_app_allowed — gate invariants
# ---------------------------------------------------------------------------

class TestCheckAppAllowed(unittest.TestCase):
    def test_benign_idempotent_pass(self):
        # Idempotence: repeated calls on benign input keep passing.
        with dh_env():
            for _ in range(3):
                safety.check_app_allowed("TextEdit", "com.apple.TextEdit")

    def test_sensitive_names_raise_idempotently(self):
        # Idempotence: the gate raises the same PermissionError every time.
        with dh_env():
            for name in ("1Password", "Bitwarden", "Keychain Access",
                         "Monopoly Banker Helper"):  # documents broad-substring behavior
                for _ in range(2):
                    with self.assertRaises(PermissionError, msg=name):
                        safety.check_app_allowed(name, "")

    def test_sensitive_bundle_raises_with_benign_name(self):
        # Channel independence: benign display name + sensitive bundle -> raise.
        with dh_env():
            with self.assertRaises(PermissionError):
                safety.check_app_allowed("Totally Benign App", "com.agilebits.1password")

    def test_error_message_contains_remediation(self):
        # Error contract: the message names the app and the escape hatch.
        with dh_env():
            with self.assertRaises(PermissionError) as cm:
                safety.check_app_allowed("1Password", "")
            msg = str(cm.exception)
            self.assertIn("1Password", msg)
            self.assertIn("DH_ALLOW_SENSITIVE", msg)

    def test_allow_sensitive_override_table(self):
        # Table-driven override semantics: exactly 1/true/yes (case-insensitive)
        # lifts the gate; every other value (including near-misses) keeps it.
        overrides = [
            ("1", True), ("true", True), ("yes", True),
            ("TRUE", True), ("Yes", True),
            ("0", False), ("false", False), ("no", False),
            ("on", False), ("2", False), (" 1", False), ("", False), (None, False),
        ]
        for value, should_allow in overrides:
            with dh_env(DH_ALLOW_SENSITIVE=value):
                ctx = self.assertRaises(PermissionError) if not should_allow else nullcontext_ok()
                if should_allow:
                    safety.check_app_allowed("1Password", "")  # must not raise
                else:
                    with self.assertRaises(PermissionError, msg=repr(value)):
                        safety.check_app_allowed("1Password", "")

    def test_empty_name_boundary(self):
        # Boundary: nothing provided -> nothing to block -> pass.
        with dh_env():
            safety.check_app_allowed("", "")


class nullcontext_ok:
    """Tiny no-op context (avoids importing contextlib.nullcontext on 3.10)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# allow_sensitive / safe_mode — env flag tables
# ---------------------------------------------------------------------------

class TestEnvFlags(unittest.TestCase):
    def test_allow_sensitive_table(self):
        table = [
            ("1", True), ("true", True), ("yes", True),
            ("TRUE", True), ("Yes", True), ("YES", True),
            ("0", False), ("false", False), ("no", False),
            ("on", False), ("2", False), (" 1", False), ("1 ", False),
            ("", False), (None, False),
        ]
        for value, expected in table:
            with dh_env(DH_ALLOW_SENSITIVE=value):
                self.assertEqual(safety.allow_sensitive(), expected, msg=repr(value))

    def test_safe_mode_table_and_default(self):
        # Default-on; only exact 0/false/no (case-insensitive) disable it.
        table = [
            (None, True),  # unset -> default "1"
            ("1", True), ("true", True), ("yes", True), ("anything", True),
            ("off", True), ("", True),
            ("0", False), ("false", False), ("no", False), ("NO", False),
        ]
        for value, expected in table:
            with dh_env(DH_SAFE=value):
                self.assertEqual(safety.safe_mode(), expected, msg=repr(value))


# ---------------------------------------------------------------------------
# check_helper_allowed — blocklist invariants
# ---------------------------------------------------------------------------

class TestCheckHelperAllowed(unittest.TestCase):
    BLOCKED = ("run_shell", "shell", "osascript_raw")
    NOT_BLOCKED = ("click_text", "labels", "open_app", "screenshot", "type_text",
                   "hotkey", "", "run_shel", "shells", "OSAScript_Raw")

    def test_blocked_names_raise_in_safe_mode(self):
        with dh_env():
            for name in self.BLOCKED:
                with self.assertRaises(PermissionError, msg=name):
                    safety.check_helper_allowed(name)

    def test_nonblocked_never_raise(self):
        # Property: the blocklist is exact-match; nothing else is ever blocked,
        # in any env configuration.
        for env in ({}, {"DH_SAFE": "1"}, {"DH_SAFE": "0"}, {"DH_ALLOW_SENSITIVE": "1"}):
            with dh_env(**env):
                for name in self.NOT_BLOCKED:
                    safety.check_helper_allowed(name)

    def test_safe_mode_off_allows_blocked(self):
        with dh_env(DH_SAFE="0"):
            for name in self.BLOCKED:
                safety.check_helper_allowed(name)

    def test_allow_sensitive_allows_blocked(self):
        with dh_env(DH_ALLOW_SENSITIVE="1"):
            for name in self.BLOCKED:
                safety.check_helper_allowed(name)

    def test_idempotent(self):
        # Idempotence: same name, same env -> same verdict on every call.
        with dh_env():
            for name in self.BLOCKED + self.NOT_BLOCKED:
                first = None
                try:
                    safety.check_helper_allowed(name)
                    first = "pass"
                except PermissionError:
                    first = "raise"
                for _ in range(5):
                    again = None
                    try:
                        safety.check_helper_allowed(name)
                        again = "pass"
                    except PermissionError:
                        again = "raise"
                    self.assertEqual(again, first, msg=name)


# ---------------------------------------------------------------------------
# check_frontmost_allowed — frontmost gate invariants (stubbed windows)
# ---------------------------------------------------------------------------

class TestCheckFrontmostAllowed(unittest.TestCase):
    def test_sensitive_frontmost_raises(self):
        front = {"name": "1Password", "bundle_id": "com.1password.mac", "pid": 4242}
        with dh_env(), fake_windows_frontmost(front):
            with self.assertRaises(PermissionError):
                safety.check_frontmost_allowed()
            # Idempotence: still raises on the second call.
            with self.assertRaises(PermissionError):
                safety.check_frontmost_allowed()

    def test_benign_frontmost_passes(self):
        front = {"name": "TextEdit", "bundle_id": "com.apple.TextEdit", "pid": 100}
        with dh_env(), fake_windows_frontmost(front):
            safety.check_frontmost_allowed()

    def test_none_frontmost_passes(self):
        # Boundary: no frontmost app reported -> nothing to gate.
        with dh_env(), fake_windows_frontmost(None):
            safety.check_frontmost_allowed()

    def test_frontmost_app_failure_passes_silently(self):
        # Failure-safety: perception errors must never block or crash the gate.
        with dh_env(), fake_windows_frontmost(_RAISE):
            safety.check_frontmost_allowed()

    def test_missing_name_keys_passes(self):
        # Boundary: dict present but empty identity fields -> pass.
        with dh_env(), fake_windows_frontmost({"name": "", "bundle_id": ""}):
            safety.check_frontmost_allowed()

    def test_override_allows_sensitive_frontmost(self):
        front = {"name": "Bitwarden", "bundle_id": "com.bitwarden.desktop", "pid": 7}
        with dh_env(DH_ALLOW_SENSITIVE="1"), fake_windows_frontmost(front):
            safety.check_frontmost_allowed()


# ---------------------------------------------------------------------------
# audit — append-only log invariants
# ---------------------------------------------------------------------------

class TestAuditProperties(unittest.TestCase):
    def test_append_only_roundtrip_monotonic(self):
        # Invariants: exactly one JSON line per call; each line roundtrips
        # (event + detail preserved); ts is non-decreasing and not in the future.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "audit.jsonl"
            events = [
                ("open_app", {"app": "TextEdit"}),
                ("click_text", {"text": "Save", "exact": True}),
                ("activate", None),
                ("screenshot", {"app": "Safari", "window_id": 12, "path": "/tmp/x.png"}),
            ]
            with mock.patch.object(safety, "_AUDIT", target):
                for ev, detail in events:
                    safety.audit(ev, detail)
                # Idempotence of growth: a repeat call appends exactly one more line.
                safety.audit("activate", None)
            lines = target.read_text().splitlines()
            self.assertEqual(len(lines), len(events) + 1)
            rows = [json.loads(line) for line in lines]
            for row, (ev, detail) in zip(rows, events):
                self.assertEqual(row["event"], ev)
                self.assertEqual(row["detail"], detail or {})
            extra = rows[-1]
            self.assertEqual(extra["event"], "activate")
            self.assertEqual(extra["detail"], {})
            ts = [r["ts"] for r in rows]
            self.assertEqual(ts, sorted(ts), msg="audit ts must be non-decreasing")
            self.assertTrue(all(t <= time.time() + 1 for t in ts))

    def test_non_serializable_detail_never_raises(self):
        # Failure-safety: default=str must absorb arbitrary objects; the log
        # stays valid JSONL.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "audit.jsonl"
            with mock.patch.object(safety, "_AUDIT", target):
                safety.audit("weird", {"obj": object(), "p": Path(tmp), "s": {"inner"}})
            rows = [json.loads(line) for line in target.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event"], "weird")
            self.assertEqual(rows[0]["detail"]["p"], str(Path(tmp)))

    def test_unwritable_path_never_raises(self):
        # Failure-safety: a broken audit location must never crash the caller
        # (documented TR-4 behavior: silent suppression — this pins it as an
        # observable invariant, not an accident).
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("i am a file, not a directory")
            bad = blocker / "sub" / "audit.jsonl"
            with mock.patch.object(safety, "_AUDIT", bad):
                safety.audit("x", {})
                safety.audit("x", {})  # repeated: still silent

    def test_default_detail_is_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "audit.jsonl"
            with mock.patch.object(safety, "_AUDIT", target):
                safety.audit("no_detail")
            row = json.loads(target.read_text().splitlines()[0])
            self.assertEqual(row["detail"], {})
            self.assertEqual(row["event"], "no_detail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
