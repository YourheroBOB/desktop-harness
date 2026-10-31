"""Unit and integration tests for fmb_feature2 advanced_helpers."""
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from fmb_feature2 import advanced_helpers


class TestWaitFor(unittest.TestCase):
    """Test wait_for polling and timeout mechanisms."""

    def test_wait_for_callable_immediate_success(self):
        called = 0

        def cond():
            nonlocal called
            called += 1
            return {"found": True}

        res = advanced_helpers.wait_for(cond, timeout=1.0, interval=0.01)
        self.assertEqual(res, {"found": True})
        self.assertEqual(called, 1)

    def test_wait_for_callable_delayed_success(self):
        attempts = 0

        def cond():
            nonlocal attempts
            attempts += 1
            if attempts >= 3:
                return "ready"
            return None

        res = advanced_helpers.wait_for(cond, timeout=1.0, interval=0.01)
        self.assertEqual(res, "ready")
        self.assertEqual(attempts, 3)

    def test_wait_for_timeout(self):
        t0 = time.time()
        with self.assertRaises(TimeoutError) as ctx:
            advanced_helpers.wait_for(lambda: None, timeout=0.1, interval=0.02)
        elapsed = time.time() - t0
        self.assertGreaterEqual(elapsed, 0.08)
        self.assertIn("timed out", str(ctx.exception))

    def test_wait_for_string_query_via_mock_find(self):
        mock_find = MagicMock(side_effect=[None, {"role": "AXButton", "title": "Submit"}])
        with patch.object(advanced_helpers, "_helpers", MagicMock(find=mock_find)):
            res = advanced_helpers.wait_for("Submit", timeout=1.0, interval=0.01)
            self.assertEqual(res["title"], "Submit")
            self.assertEqual(mock_find.call_count, 2)


class TestClipboardAndFastPaste(unittest.TestCase):
    """Test clipboard read/write and fast_paste helper."""

    def test_clipboard_set_and_get_mocked(self):
        fake_storage = {}

        class FakePB:
            def clearContents(self):
                fake_storage.clear()

            def setString_forType_(self, s, typ):
                fake_storage["text"] = s

            def stringForType_(self, typ):
                return fake_storage.get("text", "")

        fake_inst = FakePB()
        mock_nspasteboard = MagicMock()
        mock_nspasteboard.generalPasteboard.return_value = fake_inst

        with patch.object(advanced_helpers, "NSPasteboard", mock_nspasteboard), \
             patch.object(advanced_helpers, "_HAS_PYOBJC", True):
            advanced_helpers.clipboard_set("hello world from test")
            got = advanced_helpers.clipboard_get()
            self.assertEqual(got, "hello world from test")

    def test_fast_paste_invokes_hotkey_and_safety(self):
        mock_safety = MagicMock()
        mock_helpers = MagicMock()

        with patch.object(advanced_helpers, "_safety", mock_safety), \
             patch.object(advanced_helpers, "_helpers", mock_helpers), \
             patch.object(advanced_helpers, "clipboard_set") as mock_set:
            advanced_helpers.fast_paste("def foo(): return 42")
            mock_safety.check_frontmost_allowed.assert_called_once()
            mock_set.assert_called_once_with("def foo(): return 42")
            mock_helpers.hotkey.assert_called_once_with("cmd", "v")
            mock_safety.audit.assert_called_once()


class TestFocusWindowByTitle(unittest.TestCase):
    """Test focus_window_by_title ranking and activation."""

    def setUp(self):
        self.fake_windows = [
            {"id": 101, "app": "Notes", "title": "Untitled Note", "pid": 1101},
            {"id": 102, "app": "TextEdit", "title": "Project Roadmap.txt", "pid": 1102},
            {"id": 103, "app": "TextEdit", "title": "Budget.txt", "pid": 1102},
        ]

    def test_exact_and_substring_match(self):
        mock_windows = MagicMock()
        mock_windows.list_windows.return_value = self.fake_windows

        with patch.object(advanced_helpers, "_windows", mock_windows), \
             patch.object(advanced_helpers, "_HAS_PYOBJC", False):
            # Substring match
            w = advanced_helpers.focus_window_by_title("Roadmap")
            self.assertEqual(w["id"], 102)
            mock_windows.activate.assert_called_with("TextEdit")

    def test_not_found_raises_lookup_error(self):
        mock_windows = MagicMock()
        mock_windows.list_windows.return_value = self.fake_windows

        with patch.object(advanced_helpers, "_windows", mock_windows):
            with self.assertRaises(LookupError):
                advanced_helpers.focus_window_by_title("NonExistentWindow")

    def test_safety_check_intercepts(self):
        mock_safety = MagicMock()
        mock_safety.check_app_allowed.side_effect = PermissionError("Blocked")

        with patch.object(advanced_helpers, "_safety", mock_safety):
            with self.assertRaises(PermissionError):
                advanced_helpers.focus_window_by_title("Any", app="1Password")


class TestMenuClick(unittest.TestCase):
    """Test menu_click AX navigation logic."""

    def test_empty_menu_path_raises_value_error(self):
        with self.assertRaises(ValueError):
            advanced_helpers.menu_click()

    def test_menu_click_hierarchy_mock(self):
        # Build mock AX tree for File -> Save
        mock_menu_bar = "AXMenuBarRef"
        mock_file_item = "FileMenuItemRef"
        mock_save_item = "SaveMenuItemRef"
        mock_file_menu = "FileSubmenuRef"

        def fake_copy_attr(elem, attr, _):
            if elem == "AppRef" and attr == "AXMenuBar":
                return (0, mock_menu_bar)
            if elem == mock_menu_bar and attr == "AXChildren":
                return (0, [mock_file_item])
            if elem == mock_file_item and attr == "AXTitle":
                return (0, "File")
            if elem == mock_file_item and attr == "AXChildren":
                return (0, [mock_file_menu])
            if elem == mock_file_menu and attr == "AXChildren":
                return (0, [mock_save_item])
            if elem == mock_save_item and attr == "AXTitle":
                return (0, "Save")
            return (-1, None)

        action_performed = []

        def fake_perform_action(elem, act):
            action_performed.append((elem, act))
            return 0

        mock_as = MagicMock()
        mock_as.AXUIElementCreateApplication.return_value = "AppRef"
        mock_as.AXUIElementCopyAttributeValue.side_effect = fake_copy_attr
        mock_as.AXUIElementPerformAction.side_effect = fake_perform_action

        mock_windows = MagicMock()
        mock_windows.find_app.return_value = {"name": "TextEdit", "pid": 4200}

        with patch.object(advanced_helpers, "ApplicationServices", mock_as), \
             patch.object(advanced_helpers, "_windows", mock_windows), \
             patch.object(advanced_helpers, "_HAS_PYOBJC", True):
            ok = advanced_helpers.menu_click("File", "Save", app="TextEdit")
            self.assertTrue(ok)
            # Intermediate item should receive AXPress, and leaf should receive AXPress
            self.assertIn((mock_file_item, "AXPress"), action_performed)
            self.assertIn((mock_save_item, "AXPress"), action_performed)

    def test_missing_menu_segment_raises_lookup_error(self):
        mock_menu_bar = "AXMenuBarRef"
        mock_file_item = "FileMenuItemRef"

        def fake_copy_attr(elem, attr, _):
            if elem == "AppRef" and attr == "AXMenuBar":
                return (0, mock_menu_bar)
            if elem == mock_menu_bar and attr == "AXChildren":
                return (0, [mock_file_item])
            if elem == mock_file_item and attr == "AXTitle":
                return (0, "File")
            return (-1, None)

        mock_as = MagicMock()
        mock_as.AXUIElementCreateApplication.return_value = "AppRef"
        mock_as.AXUIElementCopyAttributeValue.side_effect = fake_copy_attr

        mock_windows = MagicMock()
        mock_windows.find_app.return_value = {"name": "TextEdit", "pid": 4200}

        with patch.object(advanced_helpers, "ApplicationServices", mock_as), \
             patch.object(advanced_helpers, "_windows", mock_windows), \
             patch.object(advanced_helpers, "_HAS_PYOBJC", True):
            with self.assertRaises(LookupError) as ctx:
                advanced_helpers.menu_click("Edit", "Undo", app="TextEdit")
            self.assertIn("Menu item 'Edit' not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
