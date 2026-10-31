"""Contract tests for the documented helpers / AX / windows / CLI surface.

Locks current external behaviour:
  - every helper documented in README.md / SKILL.md / HOW_IT_WORKS.md
    exists on desktop_harness.helpers and is callable
  - helpers.namespace() exposes the documented helper names (daemon exec scope)
  - desktop_harness.run exposes the console-script entry point main()
  - ax.frame_on_screen() filtering contract (visible / zero-size / off-screen)
  - windows.py record shapes: exact key sets and value types for
    list_apps / list_windows / frontmost_app / find_app misses

Discovery-only, non-mutating, no screenshots, no network. Requires macOS +
pyobjc; skipped elsewhere.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

IS_MAC = sys.platform == "darwin"

# Names documented across README.md "API surface (helpers)",
# SKILL.md "Helpers", HOW_IT_WORKS.md tables, and selftest usage.
DOCUMENTED_HELPERS = [
    "list_apps", "list_windows", "frontmost_app", "open_app", "activate",
    "find_app",
    "ax_snapshot", "labels", "button_labels", "find",
    "click_text", "set_field",
    "media_transport", "ensure_media_playing",
    "mouse_pos", "move_to", "move_by", "wiggle",
    "click", "right_click", "click_frame", "drag", "scroll",
    "type_text", "hotkey", "key",
    "screenshot",
    "enable_agent_cursor", "hide_agent_presence",
    "wait", "wait_stable", "verify",
]

APP_KEYS = {"name", "bundle_id", "pid", "active", "hidden"}
WINDOW_KEYS = {"id", "app", "pid", "title", "x", "y", "w", "h"}


@unittest.skipUnless(IS_MAC, "desktop-harness is macOS-only (pyobjc)")
class HelpersSurfaceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desktop_harness.helpers as H
        cls.H = H

    def test_documented_helpers_exist_and_are_callable(self):
        for name in DOCUMENTED_HELPERS:
            self.assertTrue(hasattr(self.H, name), name)
            self.assertTrue(callable(getattr(self.H, name)), name)

    def test_namespace_exposes_documented_helpers(self):
        ns = self.H.namespace()
        self.assertIsInstance(ns, dict)
        for name in DOCUMENTED_HELPERS:
            self.assertIn(name, ns, name)
            self.assertTrue(callable(ns[name]), name)


@unittest.skipUnless(IS_MAC, "desktop-harness is macOS-only (pyobjc)")
class RunEntryPointContract(unittest.TestCase):
    def test_run_module_exposes_console_main(self):
        import desktop_harness.run as run
        self.assertTrue(callable(run.main))


@unittest.skipUnless(IS_MAC, "desktop-harness is macOS-only (pyobjc)")
class AxFrameOnScreenContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desktop_harness.ax as ax
        cls.ax = ax

    def test_visible_frame_passes(self):
        self.assertTrue(self.ax.frame_on_screen(
            {"x": 100, "y": 100, "w": 50, "h": 50}))

    def test_zero_size_frame_fails(self):
        self.assertFalse(self.ax.frame_on_screen(
            {"x": 50, "y": 50, "w": 0, "h": 10}))

    def test_offscreen_frame_fails(self):
        self.assertFalse(self.ax.frame_on_screen(
            {"x": 100, "y": 9000, "w": 40, "h": 40}))


@unittest.skipUnless(IS_MAC, "desktop-harness is macOS-only (pyobjc)")
class WindowsRecordShapeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desktop_harness.windows as win
        cls.win = win

    def test_list_apps_record_shape(self):
        apps = self.win.list_apps()
        self.assertIsInstance(apps, list)
        for a in apps:
            self.assertEqual(set(a), APP_KEYS, a)
            self.assertIsInstance(a["name"], str)
            self.assertIsInstance(a["bundle_id"], str)
            self.assertIsInstance(a["pid"], int)
            self.assertIsInstance(a["active"], bool)
            self.assertIsInstance(a["hidden"], bool)

    def test_list_windows_record_shape(self):
        wins = self.win.list_windows()
        self.assertIsInstance(wins, list)
        for w in wins:
            self.assertEqual(set(w), WINDOW_KEYS, w)
            self.assertIsInstance(w["id"], int)
            self.assertIsInstance(w["app"], str)
            self.assertIsInstance(w["pid"], int)
            self.assertIsInstance(w["title"], str)
            for k in ("x", "y", "w", "h"):
                self.assertIsInstance(w[k], float, (k, w))

    def test_frontmost_app_shape(self):
        f = self.win.frontmost_app()
        if f is not None:
            self.assertEqual(set(f), APP_KEYS)
            self.assertIsInstance(f["pid"], int)
            self.assertIsInstance(f["active"], bool)
            self.assertIsInstance(f["hidden"], bool)

    def test_find_app_empty_query_returns_none(self):
        self.assertIsNone(self.win.find_app(""))

    def test_find_app_unknown_query_returns_none(self):
        self.assertIsNone(self.win.find_app("zzz-no-such-app-xyz-123"))


if __name__ == "__main__":
    unittest.main()
