"""固定種子 fuzz 測試：desktop-harness 的驗證、解析與轉換函式。

僅使用 Python 標準函式庫；不連線外部服務，所有暫存資料均寫入 tempfile。
可直接執行：
    python tests/test_fmb_fuzz_validation_conversion.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import socket
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch


FUZZ_SEED = 0x5EED_F02B
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_harness import daemon, safety  # noqa: E402


def _random_plain_text(rng: random.Random, max_len: int = 48) -> str:
    alphabet = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        " _-./:[]()\t\n\x00\u00a0\u4e2d\u6587\U0001f642"
    )
    return "".join(rng.choice(alphabet) for _ in range(rng.randrange(max_len + 1)))


def _random_json(rng: random.Random, depth: int = 0) -> object:
    kinds = 7 if depth < 2 else 5
    kind = rng.randrange(kinds)
    if kind == 0:
        return None
    if kind == 1:
        return rng.choice((True, False))
    if kind == 2:
        return rng.randrange(-1_000_000, 1_000_001)
    if kind == 3:
        return round(rng.uniform(-1_000_000, 1_000_000), 6)
    if kind == 4:
        return _random_plain_text(rng)
    if kind == 5:
        return [_random_json(rng, depth + 1) for _ in range(rng.randrange(5))]
    return {
        f"key-{index}": _random_json(rng, depth + 1)
        for index in range(rng.randrange(5))
    }


def _strict_json_loads(raw: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(raw, parse_constant=reject_constant)


def _fake_open_app(name: object) -> dict[str, bool]:
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    return {"opened": True}


def _fake_labels(app: object = None, limit: int = 30) -> list[str]:
    if app is not None and not isinstance(app, str):
        raise TypeError("app must be a string")
    if not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    return []


def _fake_click_text(text: object, app: object = None) -> dict[str, bool]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if app is not None and not isinstance(app, str):
        raise TypeError("app must be a string")
    return {"clicked": True}


def _fake_type_text(text: object) -> dict[str, bool]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return {"typed": True}


def _fake_hotkey(*keys: object) -> dict[str, bool]:
    if not all(isinstance(key, str) for key in keys):
        raise TypeError("keys must contain strings")
    return {"pressed": True}


def _fake_move_to(x: object, y: object, duration: float = 0.2) -> dict[str, bool]:
    float(x)
    float(y)
    float(duration)
    return {"moved": True}


def _fake_click(x: object, y: object, double: bool = False) -> dict[str, bool]:
    float(x)
    float(y)
    if not isinstance(double, bool):
        raise TypeError("double must be a boolean")
    return {"clicked": True}


def _fake_mouse_pos() -> dict[str, int]:
    return {"x": 0, "y": 0}


def _fake_wiggle() -> dict[str, bool]:
    return {"wiggled": True}


def _load_voice_tools_in_isolation() -> types.ModuleType:
    """載入真正 voice_tools.py，但以無 I/O 的 helper 取代 macOS helper。"""
    package_name = "_desktop_harness_fuzz_voice_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(SRC / "desktop_harness")]
    package.__package__ = package_name

    fake_helpers = types.ModuleType(f"{package_name}.helpers")
    fake_helpers.__package__ = package_name
    fake_helpers.list_apps = lambda: []
    fake_helpers.open_app = _fake_open_app
    fake_helpers.labels = _fake_labels
    fake_helpers.click_text = _fake_click_text
    fake_helpers.type_text = _fake_type_text
    fake_helpers.hotkey = _fake_hotkey
    fake_helpers.move_to = _fake_move_to
    fake_helpers.click = _fake_click
    fake_helpers.mouse_pos = _fake_mouse_pos
    fake_helpers.wiggle = _fake_wiggle

    package.helpers = fake_helpers
    sys.modules[package_name] = package
    sys.modules[f"{package_name}.helpers"] = fake_helpers

    module_name = f"{package_name}.voice_tools"
    spec = importlib.util.spec_from_file_location(
        module_name, SRC / "desktop_harness" / "voice_tools.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load voice_tools.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class SafetyValidationFuzzTests(unittest.TestCase):
    def test_fuzz_sensitive_checks_and_environment_parsing(self) -> None:
        rng = random.Random(FUZZ_SEED + 1)
        name_fragments = tuple(safety._SENSITIVE_NAME_SUBSTR)
        bundle_fragments = tuple(safety._SENSITIVE_BUNDLE_SUBSTR)
        blocked_helpers = ("run_shell", "shell", "osascript_raw")

        for _ in range(4096):
            name = _random_plain_text(rng)
            bundle = _random_plain_text(rng)
            if rng.random() < 0.30:
                name = rng.choice(name_fragments).upper() + _random_plain_text(rng, 16)
            if rng.random() < 0.30:
                bundle = rng.choice(bundle_fragments).upper() + _random_plain_text(rng, 16)

            allow_value = rng.choice(
                (
                    "1",
                    "true",
                    "yes",
                    "TRUE",
                    "Yes",
                    "0",
                    "false",
                    "no",
                    "",
                    " 1",
                    _random_plain_text(rng, 12).replace("\x00", ""),
                )
            )
            safe_value = rng.choice(
                (
                    "1",
                    "true",
                    "0",
                    "false",
                    "no",
                    "",
                    " 0",
                    _random_plain_text(rng, 12).replace("\x00", ""),
                )
            )
            helper = rng.choice((*blocked_helpers, _random_plain_text(rng, 16)))

            expected_allow = allow_value.lower() in ("1", "true", "yes")
            expected_safe = safe_value.lower() not in ("0", "false", "no")
            expected_sensitive = (
                any(fragment in name.lower() for fragment in name_fragments)
                or any(fragment in bundle.lower() for fragment in bundle_fragments)
            )
            expected_blocked = (
                helper in blocked_helpers and expected_safe and not expected_allow
            )

            with patch.dict(
                os.environ,
                {
                    "DH_ALLOW_SENSITIVE": allow_value,
                    "DH_SAFE": safe_value,
                },
                clear=True,
            ):
                self.assertEqual(safety.allow_sensitive(), expected_allow)
                self.assertEqual(safety.safe_mode(), expected_safe)

                if expected_sensitive and not expected_allow:
                    with self.assertRaises(PermissionError):
                        safety.check_app_allowed(name, bundle)
                else:
                    safety.check_app_allowed(name, bundle)

                if expected_blocked:
                    with self.assertRaises(PermissionError):
                        safety.check_helper_allowed(helper)
                else:
                    safety.check_helper_allowed(helper)


class VoiceParsingFuzzTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.voice = _load_voice_tools_in_isolation()

    def test_fuzz_valid_json_arguments_are_parsed_and_converted(self) -> None:
        rng = random.Random(FUZZ_SEED + 2)
        for _ in range(4096):
            value = _random_json(rng)
            encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
            output = _strict_json_loads(
                self.voice.execute("fuzz_tool", encoded, dry_run=True)
            )
            self.assertIsInstance(output, dict)
            self.assertIs(output["ok"], True)
            self.assertEqual(output["result"]["tool"], "fuzz_tool")
            self.assertIs(output["result"]["dry_run"], True)
            self.assertEqual(
                output["result"]["arguments"],
                value if value else {},
            )

    def test_fuzz_malformed_json_returns_structured_error(self) -> None:
        rng = random.Random(FUZZ_SEED + 3)
        malformed = (
            "{",
            "[",
            '{"a":}',
            '{"a" 1}',
            '{"a":1,}',
            "\x00",
            "not-json",
            "true false",
        )
        for _ in range(1024):
            raw_arguments = rng.choice(malformed) + _random_plain_text(rng, 8)
            output = _strict_json_loads(
                self.voice.execute("fuzz_tool", raw_arguments, dry_run=True)
            )
            self.assertIsInstance(output, dict)
            self.assertIs(output["ok"], False)
            self.assertIn("invalid arguments JSON", output["error"])

    def test_fuzz_tool_dispatch_never_escapes_as_an_exception(self) -> None:
        rng = random.Random(FUZZ_SEED + 4)
        tool_names = [tool["name"] for tool in self.voice.TOOL_DEFINITIONS]
        argument_names = ("name", "text", "app", "limit", "keys", "x", "y", "duration")

        for _ in range(1024):
            tool = rng.choice((*tool_names, "unknown-fuzz-tool"))
            arguments = {
                name: _random_json(rng)
                for name in rng.sample(argument_names, rng.randrange(len(argument_names) + 1))
            }
            output = _strict_json_loads(
                self.voice.execute(tool, arguments, dry_run=False)
            )
            self.assertIsInstance(output, dict)
            self.assertIsInstance(output["ok"], bool)
            if output["ok"]:
                self.assertIn("result", output)
            else:
                self.assertIn("error", output)


class AuditConversionFuzzTests(unittest.TestCase):
    def test_fuzz_audit_details_remain_one_valid_json_object_per_line(self) -> None:
        rng = random.Random(FUZZ_SEED + 5)
        with tempfile.TemporaryDirectory(prefix="dh-fuzz-audit-") as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            with patch.object(safety, "_AUDIT", audit_path):
                for _ in range(256):
                    event = _random_plain_text(rng, 32)
                    detail = _random_json(rng)
                    if not isinstance(detail, dict):
                        detail = {"value": detail}
                    safety.audit(event, detail)

            rows = [
                _strict_json_loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 256)
            for row in rows:
                self.assertIsInstance(row, dict)
                self.assertIn("ts", row)
                self.assertIn("event", row)
                self.assertIn("detail", row)


class DaemonProtocolFuzzTests(unittest.TestCase):
    def test_fuzz_client_request_round_trips_json_without_external_io(self) -> None:
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX is unavailable on this platform")

        rng = random.Random(FUZZ_SEED + 6)
        errors: list[str] = []
        requests_seen: list[dict[str, object]] = []
        stop = threading.Event()

        with tempfile.TemporaryDirectory(prefix="dh-fuzz-daemon-") as temp_dir:
            socket_path = Path(temp_dir) / "fuzz.sock"
            token_path = Path(temp_dir) / "missing.token"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(socket_path))
            server.listen(16)
            server.settimeout(0.1)

            def serve() -> None:
                while not stop.is_set():
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        continue
                    except OSError as exc:
                        if not stop.is_set():
                            errors.append(f"accept failed: {type(exc).__name__}")
                        break

                    with connection:
                        try:
                            buffer = b""
                            while b"\n" not in buffer:
                                chunk = connection.recv(65536)
                                if not chunk:
                                    raise RuntimeError("client closed before newline")
                                buffer += chunk
                            request = json.loads(buffer.decode("utf-8"))
                            if not isinstance(request, dict):
                                raise TypeError("request was not an object")
                            requests_seen.append(request)
                            response = json.dumps(
                                {
                                    "ok": True,
                                    "echo": request,
                                    "sequence": len(requests_seen),
                                },
                                ensure_ascii=True,
                            ).encode("utf-8") + b"\n"
                            connection.sendall(response)
                        except Exception as exc:
                            errors.append(f"server failed: {type(exc).__name__}: {exc}")
                            break

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            try:
                with patch.object(daemon, "SOCKET_PATH", socket_path), patch.object(
                    daemon, "TOKEN_PATH", token_path
                ):
                    for index in range(96):
                        payload: dict[str, object] = {
                            "op": "fuzz",
                            "sequence": index,
                            "data": _random_json(rng),
                        }
                        response = daemon.client_request(payload, timeout=2.0)
                        self.assertIs(response["ok"], True)
                        self.assertEqual(response["echo"], payload)
                        self.assertEqual(response["sequence"], index + 1)
            finally:
                stop.set()
                server.close()
                thread.join(timeout=2.0)

            self.assertFalse(thread.is_alive(), "local protocol server did not stop")
            self.assertEqual(errors, [])
            self.assertEqual(len(requests_seen), 96)


if __name__ == "__main__":
    unittest.main(verbosity=2)
