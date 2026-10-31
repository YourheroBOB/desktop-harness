from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class VoiceToolsEdgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        package = importlib.import_module("desktop_harness")
        source_path = Path(package.__file__).resolve().parent / "voice_tools.py"

        package_name = "_desktop_harness_fmb_edge_voice_pkg"
        helper_name = f"{package_name}.helpers"
        module_name = f"{package_name}.voice_tools"

        fake_package = types.ModuleType(package_name)
        fake_package.__path__ = []
        fake_helpers = types.ModuleType(helper_name)

        fake_helpers.list_apps = mock.Mock(return_value=[])
        fake_helpers.open_app = mock.Mock(
            return_value={"name": "FAKE_VALUE_FOR_TEST"}
        )
        fake_helpers.labels = mock.Mock(return_value=[])
        fake_helpers.click_text = mock.Mock(return_value={"hit": True})
        fake_helpers.type_text = mock.Mock(return_value=None)
        fake_helpers.hotkey = mock.Mock(return_value=None)
        fake_helpers.move_to = mock.Mock(
            return_value={"x": 0, "y": 0}
        )
        fake_helpers.click = mock.Mock(return_value=None)
        fake_helpers.mouse_pos = mock.Mock(return_value={"x": 0, "y": 0})
        fake_helpers.wiggle = mock.Mock(return_value=None)

        spec = importlib.util.spec_from_file_location(module_name, source_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load voice_tools module")

        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                package_name: fake_package,
                helper_name: fake_helpers,
                module_name: module,
            },
        ):
            spec.loader.exec_module(module)

        cls.tools = module
        cls.helpers = fake_helpers
        cls.helper_mocks = (
            fake_helpers.list_apps,
            fake_helpers.open_app,
            fake_helpers.labels,
            fake_helpers.click_text,
            fake_helpers.type_text,
            fake_helpers.hotkey,
            fake_helpers.move_to,
            fake_helpers.click,
            fake_helpers.mouse_pos,
            fake_helpers.wiggle,
        )

    def setUp(self) -> None:
        for helper_mock in self.helper_mocks:
            helper_mock.reset_mock()
            helper_mock.side_effect = None

    def test_invalid_arguments_json_returns_error_without_side_effect(self) -> None:
        response = json.loads(
            self.tools.execute("open_app", "{not-valid-json")
        )

        self.assertFalse(response["ok"])
        self.assertIn("invalid arguments JSON", response["error"])
        self.helpers.open_app.assert_not_called()

    def test_empty_string_arguments_are_treated_as_empty_mapping(self) -> None:
        response = json.loads(
            self.tools.execute("open_app", "", dry_run=True)
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["arguments"], {})
        self.helpers.open_app.assert_not_called()

    def test_dry_run_echoes_arguments_without_calling_helpers(self) -> None:
        response = json.loads(
            self.tools.execute(
                "click_xy",
                {"x": 10, "y": 20, "double": True},
                dry_run=True,
            )
        )

        self.assertTrue(response["ok"])
        self.assertTrue(response["result"]["dry_run"])
        self.assertEqual(response["result"]["tool"], "click_xy")
        self.assertEqual(
            response["result"]["arguments"],
            {"x": 10, "y": 20, "double": True},
        )
        self.helpers.click.assert_not_called()

    def test_unknown_tool_returns_structured_error(self) -> None:
        response = json.loads(
            self.tools.execute("FAKE_VALUE_FOR_TEST", {})
        )

        self.assertFalse(response["ok"])
        self.assertIn("unknown tool", response["error"])

    def test_missing_required_argument_returns_structured_error(self) -> None:
        response = json.loads(self.tools.execute("open_app", {}))

        self.assertFalse(response["ok"])
        self.assertIn("KeyError", response["error"])
        self.helpers.open_app.assert_not_called()

    def test_non_object_arguments_return_structured_error(self) -> None:
        response = json.loads(self.tools.execute("open_app", "[]"))

        self.assertFalse(response["ok"])
        self.assertIn("TypeError", response["error"])
        self.helpers.open_app.assert_not_called()

    def test_invalid_numeric_argument_returns_structured_error(self) -> None:
        response = json.loads(
            self.tools.execute(
                "move_mouse",
                {"x": "not-a-number", "y": 20},
            )
        )

        self.assertFalse(response["ok"])
        self.assertIn("ValueError", response["error"])
        self.assertIn("not-a-number", response["error"])
        self.helpers.move_to.assert_not_called()

    def test_helper_exception_is_returned_as_structured_error(self) -> None:
        self.helpers.type_text.side_effect = PermissionError(
            "FAKE_VALUE_FOR_TEST"
        )

        response = json.loads(
            self.tools.execute("type_text", {"text": "FAKE_VALUE_FOR_TEST"})
        )

        self.assertFalse(response["ok"])
        self.assertIn("PermissionError", response["error"])
        self.assertIn("FAKE_VALUE_FOR_TEST", response["error"])

    def test_tool_schema_names_and_required_arguments_are_consistent(self) -> None:
        definitions = self.tools.TOOL_DEFINITIONS
        names = [definition["name"] for definition in definitions]

        self.assertEqual(len(names), len(set(names)))
        for definition in definitions:
            with self.subTest(tool=definition["name"]):
                self.assertEqual(definition["type"], "function")
                parameters = definition["parameters"]
                self.assertEqual(parameters["type"], "object")
                self.assertIsInstance(parameters.get("required", []), list)
                for required_name in parameters.get("required", []):
                    self.assertIn(required_name, parameters.get("properties", {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
