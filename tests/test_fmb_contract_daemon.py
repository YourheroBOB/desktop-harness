"""Contract tests for desktop_harness.daemon public surface (no live serving).

Locks current external behaviour:
  - SOCKET_PATH / TOKEN_PATH env overrides; PID_PATH sibling naming
  - is_running() -> False when no socket exists
  - client_request() -> OSError when socket missing (no hang, no network)
  - token helpers: _write_token() 48-hex + 0600 mode; _read_token() semantics
  - _pid_alive() semantics

All paths point at a tmp dir; no real daemon is started, nothing outside
the tmp dir is touched.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_ENV_KEYS = ("DH_SOCKET", "DH_TOKEN_PATH")


class DaemonContractTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._sock = Path(self._tmp.name) / "daemon.sock"
        self._tok = Path(self._tmp.name) / "daemon.token"
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ["DH_SOCKET"] = str(self._sock)
        os.environ["DH_TOKEN_PATH"] = str(self._tok)
        import desktop_harness.daemon as d
        self.d = importlib.reload(d)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()
        import desktop_harness.daemon as d
        importlib.reload(d)

    def test_paths_respect_env_overrides(self):
        self.assertEqual(self.d.SOCKET_PATH, self._sock)
        self.assertEqual(self.d.socket_path(), self._sock)
        self.assertEqual(self.d.TOKEN_PATH, self._tok)

    def test_pid_path_is_sibling_of_socket(self):
        self.assertEqual(self.d.PID_PATH, self._sock.with_suffix(".pid"))
        self.assertEqual(self.d.PID_PATH.name,
                         self._sock.stem + ".pid")

    def test_is_running_false_without_socket(self):
        self.assertFalse(self.d.is_running())

    def test_client_request_missing_socket_raises_oserror(self):
        with self.assertRaises(OSError):
            self.d.client_request({"op": "ping"}, timeout=0.5)

    def test_write_token_shape_and_permissions(self):
        tok = self.d._write_token()
        self.assertIsInstance(tok, str)
        self.assertEqual(len(tok), 48)
        self.assertIsNotNone(int(tok, 16))  # pure hex
        self.assertTrue(self._tok.exists())
        self.assertEqual(self._tok.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.d._read_token(), tok)

    def test_read_token_missing_file_returns_none(self):
        self.assertIsNone(self.d._read_token())

    def test_read_token_empty_or_blank_returns_none(self):
        self._tok.write_text("")
        self.assertIsNone(self.d._read_token())
        self._tok.write_text("   \n")
        self.assertIsNone(self.d._read_token())

    def test_read_token_strips_surrounding_whitespace(self):
        self._tok.write_text("abc123 \n")
        self.assertEqual(self.d._read_token(), "abc123")

    def test_pid_alive_own_pid_true_and_unused_pid_false(self):
        self.assertTrue(self.d._pid_alive(os.getpid()))
        self.assertFalse(self.d._pid_alive(999999999))


if __name__ == "__main__":
    unittest.main()
