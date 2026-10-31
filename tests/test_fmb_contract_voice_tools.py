"""Contract tests for desktop_harness.voice_tools public surface.

Locks current external behaviour:
  - TOOL_DEFINITIONS: exact tool-name set + per-tool JSON schema shape
  - execute() dry-run JSON envelope {"ok":true,"result":{dry_run,tool,arguments}}
  - execute() error envelopes: unknown tool / invalid arguments JSON
  - handlers() key set and dry-run behaviour
  - SESSION_INSTRUCTIONS content markers

Only dry-run / error paths are exercised — no GUI actions, no network,
no real mouse or keyboard events. Requires macOS + pyobjc to import the
module (voice_tools pulls in helpers); skipped elsewhere.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

IS_MAC = sys.platform == "darwin"

EXPECTED_TOOLS = {
    "list_apps", "open_app", "screen_labels", "click_text", "type_text",
    "hotkey", "move_mouse", "click_xy", "mouse_pos", "wiggle_mouse",
}

EXPECTED_REQUIRED = {
    "list_apps": [],
    "open_app": ["name"],
    "screen_labels": [],
    "click_text": ["text"],
    "type_text": ["text"],
    "hotkey": ["keys"],
    "move_mouse": ["x", "y"],
    "click_xy": ["x", "y"],
    "mouse_pos": [],
    "wiggle_mouse": [],
}


@unittest.skipUnless(IS_MAC, "desktop-harness is macOS-only (pyobjc)")
class VoiceToolSchemaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desktop_harness.voice_tools as vt
        cls.vt = vt

    def test_tool_definition_shape(self):
        names = [t["name"] for t in self.vt.TOOL_DEFINITIONS]
        self.assertEqual(len(names), len(set(names)), "tool names must be unique")
        for t in self.vt.TOOL_DEFINITIONS:
            self.assertEqual(t["type"], "function", t["name"])
            self.assertIsInstance(t["name"], str)
            self.assertTrue(t["name"])
            self.assertIsInstance(t["description"], str)
            self.assertTrue(t["description"].strip(), t["name"])
            params = t["parameters"]
            self.assertIsInstance(params, dict)
            self.assertEqual(params.get("type"), "object", t["name"])
            self.assertIsInstance(params.get("properties"), dict, t["name"])
            self.assertIsInstance(params.get("required"), list, t["name"])
            for req in params["required"]:
                self.assertIn(req, params["properties"], t["name"])
            for prop in params["properties"].values():
                self.assertIn("type", prop, t["name"])

    def test_tool_names_exact_set(self):
        names = {t["name"] for t in self.vt.TOOL_DEFINITIONS}
        self.assertEqual(names, EXPECTED_TOOLS)

    def test_required_parameters_per_tool(self):
        by_name = {t["name"]: t for t in self.vt.TOOL_DEFINITIONS}
        for name, req in EXPECTED_REQUIRED.items():
            self.assertEqual(by_name[name]["parameters"]["required"], req, name)


@unittest.skipUnless(IS_MAC, "desktop-harness is macOS-only (pyobjc)")
class VoiceToolExecuteContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desktop_harness.voice_tools as vt
        cls.vt = vt

    def test_execute_dry_run_envelope_for_every_tool(self):
        for name in sorted(EXPECTED_TOOLS):
            out = self.vt.execute(name, {}, dry_run=True)
            obj = json.loads(out)
            self.assertEqual(
                obj,
                {"ok": True,
                 "result": {"dry_run": True, "tool": name, "arguments": {}}},
                name,
            )

    def test_execute_dry_run_parses_json_string_arguments(self):
        out = self.vt.execute("click_text", '{"text": "Save"}', dry_run=True)
        obj = json.loads(out)
        self.assertTrue(obj["ok"])
        self.assertEqual(obj["result"]["arguments"], {"text": "Save"})

    def test_execute_dry_run_accepts_dict_arguments(self):
        out = self.vt.execute("move_mouse", {"x": 11, "y": 22}, dry_run=True)
        obj = json.loads(out)
        self.assertEqual(obj["result"]["arguments"], {"x": 11, "y": 22})

    def test_execute_unknown_tool_error_envelope(self):
        obj = json.loads(self.vt.execute("nope", {}, dry_run=False))
        self.assertEqual(obj, {"ok": False, "error": "unknown tool: nope"})

    def test_execute_invalid_arguments_json_error_envelope(self):
        obj = json.loads(self.vt.execute("click_text", "{not json", dry_run=True))
        self.assertFalse(obj["ok"])
        self.assertIn("invalid arguments JSON", obj["error"])


@unittest.skipUnless(IS_MAC, "desktop-harness is macOS-only (pyobjc)")
class VoiceToolHandlersContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desktop_harness.voice_tools as vt
        cls.vt = vt

    def test_handlers_key_set_matches_tool_definitions(self):
        for dry in (True, False):
            self.assertEqual(set(self.vt.handlers(dry_run=dry)), EXPECTED_TOOLS)

    def test_handlers_are_callable_and_respect_dry_run(self):
        h = self.vt.handlers(dry_run=True)
        for name, fn in h.items():
            self.assertTrue(callable(fn), name)
        obj = json.loads(h["mouse_pos"]())
        self.assertTrue(obj["ok"])
        self.assertTrue(obj["result"]["dry_run"])

    def test_session_instructions_content_markers(self):
        s = self.vt.SESSION_INSTRUCTIONS
        self.assertIsInstance(s, str)
        self.assertTrue(s.strip())
        self.assertIn("screen_labels", s)
        self.assertIn("click_text", s)
        self.assertIn("confirm", s.lower())


if __name__ == "__main__":
    unittest.main()
