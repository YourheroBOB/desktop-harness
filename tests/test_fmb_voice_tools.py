"""Tests for desktop_harness.voice_tools — tool schema shape + dry-run executor.

dry_run=True never touches the GUI; these tests exercise only schema validation
and the pure argument-parsing / error paths. No network, no mic, no mouse.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

pytest.importorskip("Quartz")  # voice_tools imports helpers → pyobjc

try:
    from desktop_harness import voice_tools as vt
except Exception as e:  # pragma: no cover - environment dependent
    pytest.skip(f"voice_tools not importable here: {e}", allow_module_level=True)


def test_tool_definitions_shape():
    names = [t["name"] for t in vt.TOOL_DEFINITIONS]
    assert len(names) == len(set(names)), "tool names must be unique"
    for t in vt.TOOL_DEFINITIONS:
        assert t["type"] == "function"
        assert isinstance(t["name"], str) and t["name"]
        assert isinstance(t["description"], str) and t["description"]
        params = t["parameters"]
        assert params["type"] == "object"
        assert set(params) <= {"type", "properties", "required"}
        for r in params.get("required", []):
            assert r in params["properties"], (
                f"tool {t['name']}: required param {r!r} missing from properties"
            )


def test_expected_core_tools_present():
    names = {t["name"] for t in vt.TOOL_DEFINITIONS}
    for expected in ("list_apps", "open_app", "screen_labels", "click_text",
                     "type_text", "hotkey", "move_mouse", "click_xy", "mouse_pos"):
        assert expected in names


def test_execute_dry_run_never_acts():
    out = json.loads(vt.execute("open_app", {"name": "FAKE_VALUE_FOR_TEST"}, dry_run=True))
    assert out["ok"] is True
    assert out["result"]["dry_run"] is True
    assert out["result"]["tool"] == "open_app"
    assert out["result"]["arguments"] == {"name": "FAKE_VALUE_FOR_TEST"}


def test_execute_unknown_tool_errors():
    out = json.loads(vt.execute("FAKE_TOOL_FOR_TEST", {}, dry_run=True))
    assert out["ok"] is False
    assert "unknown tool" in out["error"]


def test_execute_invalid_arguments_json_errors():
    out = json.loads(vt.execute("click_text", "{not valid json", dry_run=True))
    assert out["ok"] is False
    assert "invalid arguments JSON" in out["error"]


def test_execute_empty_string_arguments_become_empty_dict():
    out = json.loads(vt.execute("mouse_pos", "", dry_run=True))
    assert out["ok"] is True
    assert out["result"]["arguments"] == {}


def test_execute_none_arguments_become_empty_dict():
    out = json.loads(vt.execute("mouse_pos", None, dry_run=True))
    assert out["ok"] is True
    assert out["result"]["arguments"] == {}


def test_handlers_map_covers_all_tools_and_is_dry_runnable():
    hs = vt.handlers(dry_run=True)
    assert set(hs) == {t["name"] for t in vt.TOOL_DEFINITIONS}
    out = json.loads(hs["mouse_pos"]())
    assert out["ok"] is True


def test_session_instructions_sanity():
    assert isinstance(vt.SESSION_INSTRUCTIONS, str)
    assert len(vt.SESSION_INSTRUCTIONS) > 50
    # consent rule must be present for a real-Mac voice agent
    assert "confirm" in vt.SESSION_INSTRUCTIONS.lower()
