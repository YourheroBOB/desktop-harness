"""Tests for desktop_harness.daemon — token handling, client wire protocol, serve().

Everything runs against tmp_path sockets:
  - a MockDaemon thread implements the documented NDJSON protocol
  - small one-shot servers reproduce the two "connection dropped" failure modes
  - one integration test runs the real serve() with a mocked helpers.namespace
    (no real GUI helpers, no repo-external paths, no network)

Note: the mock server's response builder is named ``_respond_to`` rather than
``_handle`` on purpose — CPython 3.13's ``threading.Thread`` sets an instance
attribute ``self._handle`` (a ``_thread._ThreadHandle``) inside ``start()``,
which would shadow a method of that name and blow up the thread.
"""
from __future__ import annotations

import importlib
import json
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from desktop_harness import daemon as d  # noqa: E402

TOKEN = "FAKE_VALUE_FOR_TEST_daemon_token"


# ---------------------------------------------------------------- helpers


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Point the daemon module's path constants at tmp_path."""
    p = SimpleNamespace(
        sock=tmp_path / "daemon.sock",
        token_file=tmp_path / "daemon.token",
        pid=tmp_path / "daemon.pid",
    )
    monkeypatch.setattr(d, "SOCKET_PATH", p.sock)
    monkeypatch.setattr(d, "PID_PATH", p.pid)
    monkeypatch.setattr(d, "TOKEN_PATH", p.token_file)
    return p


class MockDaemon(threading.Thread):
    """Minimal stand-in implementing the daemon wire protocol for one request."""

    def __init__(self, sock_path: Path, token: str | None):
        super().__init__(daemon=True)
        self.sock_path = Path(sock_path)
        self.token = token
        self.requests = []
        self.errors = []
        self.ready = threading.Event()

    def run(self):
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            srv.bind(str(self.sock_path))
            srv.listen(4)
            self.ready.set()
            conn, _ = srv.accept()
            with conn:
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                if not buf:
                    return
                req = json.loads(buf.decode())
                self.requests.append(req)
                conn.sendall((json.dumps(self._respond_to(req)) + "\n").encode())
        except Exception as e:  # surface failures in the test thread, not pytest warnings
            self.errors.append(e)
        finally:
            srv.close()

    def _respond_to(self, req):
        if self.token is not None and req.get("token") != self.token:
            return {"ok": False, "error": "unauthorized (bad or missing token)"}
        op = req.get("op")
        if op == "ping":
            return {"ok": True, "pong": True}
        if op == "exec":
            return {"ok": True, "stdout": "mock", "stderr": ""}
        return {"ok": False, "error": f"unknown op {op}"}

    def join_checked(self, timeout: float = 5.0):
        self.join(timeout)
        assert not self.is_alive(), "mock daemon thread did not finish"
        assert not self.errors, f"mock daemon thread raised: {self.errors[0]!r}"


def _start_server(paths, handler):
    """One-shot AF_UNIX server on paths.sock; handler(conn) runs on a thread."""
    started = threading.Event()
    errors = []

    def run():
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            srv.bind(str(paths.sock))
            srv.listen(1)
            started.set()
            conn, _ = srv.accept()
            with conn:
                handler(conn)
        except Exception as e:
            errors.append(e)
        finally:
            srv.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert started.wait(5), "test server never came up"
    return SimpleNamespace(thread=t, errors=errors)


def _drain_until_newline(conn) -> bytes:
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(65536)
        if not chunk:
            break
        buf += chunk
    return buf


def _wait_until(cond, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------- token file


def test_write_token_creates_0600_hex_file(paths):
    tok = d._write_token()
    assert paths.token_file.exists()
    if sys.platform != "win32":
        assert (paths.token_file.stat().st_mode & 0o777) == 0o600
    assert len(tok) == 48
    assert all(c in "0123456789abcdef" for c in tok)
    assert d._read_token() == tok
    # each start generates a fresh token
    assert d._write_token() != tok


def test_read_token_missing_or_blank_file(paths):
    assert d._read_token() is None
    paths.token_file.write_text("   \n", encoding="utf-8")
    assert d._read_token() is None


# ---------------------------------------------------------------- is_running / no daemon


def test_is_running_false_without_socket(paths):
    assert d.is_running() is False


def test_client_raises_when_socket_missing(paths):
    with pytest.raises(OSError):
        d.client_request({"op": "ping"}, timeout=5)


# ------------------------------------------- peer hangs up without answering


def test_client_raises_runtime_error_when_daemon_closes_after_reading(paths):
    """Documented contract: EOF on the reply stream → RuntimeError('closed connection').

    The server consumes the whole request and then closes, so the FIN is clean
    (no reset) — this is the deterministic, generic "daemon died" path.
    """

    def handler(conn):
        _drain_until_newline(conn)
        # deliberately no reply → client sees EOF

    srv = _start_server(paths, handler)
    with pytest.raises(RuntimeError, match="closed connection"):
        d.client_request({"op": "ping"}, timeout=5)
    srv.thread.join(5)


def test_client_surfaces_error_on_abrupt_peer_reset(paths):
    """Closing with unread request data resets the connection — client must fail fast.

    We only assert "some socket-level error, not a hang"; the exact type is
    pinned by the xfail below.
    """

    def handler(conn):
        conn.recv(1)  # leave the rest of the request unread → close sends RST

    srv = _start_server(paths, handler)
    with pytest.raises((RuntimeError, OSError)) as ei:
        d.client_request({"op": "ping"}, timeout=5)
    assert not isinstance(ei.value, TimeoutError), "client hung instead of failing fast"
    srv.thread.join(5)


@pytest.mark.xfail(
    reason=(
        "product behaviour, source not changed in this task: "
        "daemon.client_request documents RuntimeError('daemon closed connection'), "
        "but an abrupt peer reset (server closes with unread request data) leaks "
        "ConnectionResetError out of socket.recv instead of normalising it. "
        "Callers catching only RuntimeError would see an unexpected OSError."
    ),
    strict=False,
)
def test_client_normalizes_abrupt_reset_to_runtime_error(paths):
    def handler(conn):
        conn.recv(1)

    srv = _start_server(paths, handler)
    with pytest.raises(RuntimeError, match="closed connection"):
        d.client_request({"op": "ping"}, timeout=5)
    srv.thread.join(5)


# ---------------------------------------------------------------- client protocol vs mock daemon


def test_client_auto_attaches_token_from_file(paths):
    paths.token_file.write_text(TOKEN + "\n", encoding="utf-8")
    md = MockDaemon(paths.sock, token=TOKEN)
    md.start()
    assert md.ready.wait(5)
    resp = d.client_request({"op": "ping"}, timeout=5)
    assert resp == {"ok": True, "pong": True}
    assert md.requests[0]["op"] == "ping"
    assert md.requests[0]["token"] == TOKEN
    md.join_checked()


def test_client_without_token_file_is_unauthorized(paths):
    # no token file → client sends no token → mock daemon (like the real one) rejects
    md = MockDaemon(paths.sock, token=TOKEN)
    md.start()
    assert md.ready.wait(5)
    resp = d.client_request({"op": "ping"}, timeout=5)
    assert resp["ok"] is False
    assert "unauthorized" in resp["error"]
    assert "token" not in md.requests[0]
    md.join_checked()


def test_client_does_not_overwrite_explicit_token(paths):
    paths.token_file.write_text(TOKEN + "\n", encoding="utf-8")
    md = MockDaemon(paths.sock, token=TOKEN)
    md.start()
    assert md.ready.wait(5)
    resp = d.client_request({"op": "ping", "token": "FAKE_VALUE_FOR_TEST_wrong"}, timeout=5)
    assert resp["ok"] is False
    assert md.requests[0]["token"] == "FAKE_VALUE_FOR_TEST_wrong"
    md.join_checked()


def test_exec_via_daemon_wraps_op_and_code(paths):
    paths.token_file.write_text(TOKEN, encoding="utf-8")
    md = MockDaemon(paths.sock, token=TOKEN)
    md.start()
    assert md.ready.wait(5)
    resp = d.exec_via_daemon("print(1+1)", timeout=5)
    assert resp["ok"] is True
    req = md.requests[0]
    assert req["op"] == "exec"
    assert req["code"] == "print(1+1)"
    assert req["token"] == TOKEN
    md.join_checked()


# ---------------------------------------------------------------- real serve() integration


@pytest.mark.skipif(sys.platform != "darwin", reason="serve() imports macOS frameworks")
def test_serve_roundtrip_auth_and_exec(paths, monkeypatch):
    pytest.importorskip("Quartz")
    try:
        helpers = importlib.import_module("desktop_harness.helpers")
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"desktop_harness.helpers not importable here: {e}")

    # Mock the namespace so serve() never touches real GUI helpers.
    monkeypatch.setattr(helpers, "namespace", lambda: {"RESULT": []})

    t = threading.Thread(target=d.serve, daemon=True)
    t.start()
    try:
        assert _wait_until(lambda: paths.sock.exists()), "daemon socket never appeared"
        assert _wait_until(lambda: d.is_running()), "daemon never answered ping"

        # 1) unauthenticated request rejected (raw socket, no token)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect(str(paths.sock))
            s.sendall((json.dumps({"op": "ping"}) + "\n").encode())
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
        resp = json.loads(buf.decode())
        assert resp["ok"] is False
        assert "unauthorized" in resp["error"]

        # 2) authenticated exec captures stdout
        out = d.exec_via_daemon("print(1+1)", timeout=10)
        assert out["ok"] is True
        assert out["stdout"].strip() == "2"

        # 3) exec error → ok=False, traceback in stderr
        out = d.exec_via_daemon("raise ValueError('FAKE_VALUE_FOR_TEST')", timeout=10)
        assert out["ok"] is False
        assert "ValueError" in out["stderr"]

        # 4) unknown op rejected
        resp = d.client_request({"op": "FAKE_OP_FOR_TEST"}, timeout=10)
        assert resp["ok"] is False
        assert "unknown op" in resp["error"]
    finally:
        try:
            d.client_request({"op": "quit"}, timeout=5)
        except Exception:
            pass

    t.join(8)
    assert not t.is_alive(), "serve() did not exit after quit"
    assert not paths.sock.exists(), "socket file not cleaned up"
    assert not paths.pid.exists(), "pid file not cleaned up"
