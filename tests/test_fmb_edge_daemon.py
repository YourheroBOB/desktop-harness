from __future__ import annotations

import importlib
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_harness import daemon


class DaemonProtocolEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        temp_root = Path(self._temp_dir.name)

        package = importlib.import_module("desktop_harness")
        fake_helpers = types.ModuleType("desktop_harness.helpers")
        fake_helpers.namespace = lambda: {}

        patchers = (
            mock.patch.object(daemon, "SOCKET_PATH", temp_root / "daemon.sock"),
            mock.patch.object(daemon, "PID_PATH", temp_root / "daemon.pid"),
            mock.patch.object(daemon, "TOKEN_PATH", temp_root / "daemon.token"),
            mock.patch.dict(
                sys.modules,
                {"desktop_harness.helpers": fake_helpers},
            ),
            mock.patch.object(package, "helpers", fake_helpers, create=True),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.server_errors: list[BaseException] = []

        def serve() -> None:
            try:
                daemon.serve()
            except BaseException as exc:  # pragma: no cover - surfaced by assertion
                self.server_errors.append(exc)

        self.server_thread = threading.Thread(target=serve, daemon=True)
        self.server_thread.start()
        self.addCleanup(self._stop_server)
        self._wait_for_server()

    def _wait_for_server(self) -> None:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if daemon.SOCKET_PATH.exists() and daemon.PID_PATH.exists():
                return
            if not self.server_thread.is_alive():
                break
            time.sleep(0.01)

        self.fail(
            "daemon did not start: "
            f"errors={[type(exc).__name__ for exc in self.server_errors]}"
        )

    def _stop_server(self) -> None:
        try:
            if daemon.SOCKET_PATH.exists():
                daemon.client_request({"op": "quit"}, timeout=1.0)
        except Exception:
            pass
        self.server_thread.join(timeout=3.0)

    def _raw_request(
        self,
        payload: dict | None = None,
        *,
        raw: bytes | None = None,
    ) -> dict:
        if raw is None:
            raw = (json.dumps(payload or {}) + "\n").encode("utf-8")

        chunks: list[bytes] = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(str(daemon.SOCKET_PATH))
            client.sendall(raw)
            while True:
                chunk = client.recv(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break

        self.assertTrue(chunks, "daemon returned an empty response")
        return json.loads(b"".join(chunks).decode("utf-8"))

    def test_missing_and_incorrect_authentication_are_rejected(self) -> None:
        missing = self._raw_request({"op": "ping"})
        self.assertFalse(missing["ok"])
        self.assertIn("unauthorized", missing["error"].lower())

        incorrect = self._raw_request(
            {"op": "ping", "token": "FAKE_VALUE_FOR_TEST"}
        )
        self.assertFalse(incorrect["ok"])
        self.assertIn("unauthorized", incorrect["error"].lower())

        valid = daemon.client_request({"op": "ping"})
        self.assertTrue(valid["ok"])
        self.assertTrue(valid["pong"])

    def test_malformed_json_returns_error_without_stopping_daemon(self) -> None:
        response = self._raw_request(raw=b'{"op":\n')

        self.assertFalse(response["ok"])
        self.assertTrue(response["error"])

        ping = daemon.client_request({"op": "ping"})
        self.assertTrue(ping["ok"])
        self.assertTrue(ping["pong"])

    def test_unknown_operation_returns_structured_error(self) -> None:
        response = daemon.client_request({"op": "FAKE_VALUE_FOR_TEST"})

        self.assertFalse(response["ok"])
        self.assertIn("unknown op", response["error"])

    def test_exec_reports_stdout_runtime_errors_and_syntax_errors(self) -> None:
        successful = daemon.client_request(
            {"op": "exec", "code": "print('FAKE_VALUE_FOR_TEST')"}
        )
        self.assertTrue(successful["ok"])
        self.assertIn("FAKE_VALUE_FOR_TEST", successful["stdout"])

        runtime_error = daemon.client_request(
            {
                "op": "exec",
                "code": "raise RuntimeError('FAKE_VALUE_FOR_TEST')",
            }
        )
        self.assertFalse(runtime_error["ok"])
        self.assertIn("RuntimeError", runtime_error["stderr"])
        self.assertIn("FAKE_VALUE_FOR_TEST", runtime_error["stderr"])

        syntax_error = daemon.client_request(
            {"op": "exec", "code": "if True print('FAKE_VALUE_FOR_TEST')"}
        )
        self.assertFalse(syntax_error["ok"])
        self.assertIn("SyntaxError", syntax_error["stderr"])

    def test_quit_cleans_socket_and_pid_but_keeps_token_file(self) -> None:
        response = daemon.client_request({"op": "quit"}, timeout=2.0)
        self.assertTrue(response["ok"])

        self.server_thread.join(timeout=3.0)
        self.assertFalse(self.server_thread.is_alive())
        self.assertFalse(daemon.SOCKET_PATH.exists())
        self.assertFalse(daemon.PID_PATH.exists())
        self.assertTrue(daemon.TOKEN_PATH.exists())

    def test_socket_token_and_pid_are_owner_only(self) -> None:
        self.assertEqual(
            stat.S_IMODE(daemon.SOCKET_PATH.stat().st_mode),
            0o600,
        )
        self.assertEqual(
            stat.S_IMODE(daemon.TOKEN_PATH.stat().st_mode),
            0o600,
        )
        self.assertEqual(
            stat.S_IMODE(daemon.PID_PATH.stat().st_mode),
            0o600,
        )

    def test_client_request_does_not_mutate_caller_payload(self) -> None:
        payload = {"op": "ping"}

        response = daemon.client_request(payload)

        self.assertTrue(response["ok"])
        self.assertNotIn("token", payload)

    def test_second_process_refuses_to_replace_live_daemon(self) -> None:
        package = importlib.import_module("desktop_harness")
        source_root = str(Path(package.__file__).resolve().parent.parent)
        env = os.environ.copy()
        env["DH_SOCKET"] = str(daemon.SOCKET_PATH)
        env["DH_TOKEN_PATH"] = str(daemon.TOKEN_PATH)
        env["PYTHONPATH"] = os.pathsep.join(
            value
            for value in (source_root, env.get("PYTHONPATH", ""))
            if value
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        child_code = """
import sys
import types

helper = types.ModuleType('desktop_harness.helpers')
helper.namespace = lambda: {}
sys.modules['desktop_harness.helpers'] = helper

from desktop_harness import daemon
daemon.serve()
"""
        result = subprocess.run(
            [sys.executable, "-c", child_code],
            env=env,
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already running", result.stderr)
        self.assertTrue(daemon.SOCKET_PATH.exists())

        ping = daemon.client_request({"op": "ping"})
        self.assertTrue(ping["ok"])
        self.assertTrue(ping["pong"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
