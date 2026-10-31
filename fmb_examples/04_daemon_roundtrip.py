#!/usr/bin/env python3
"""Exercise an isolated local daemon without using the user's daemon."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PREFIX = "EXAMPLE_RESULT="


def harness_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.is_file() else sys.executable


def request(socket_path: Path, token: str, payload: dict[str, object]) -> dict:
    request_data = dict(payload)
    request_data["token"] = token
    encoded = (json.dumps(request_data) + "\n").encode("utf-8")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(socket_path))
        client.sendall(encoded)
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break

    raw = b"".join(chunks)
    if not raw:
        raise RuntimeError("daemon returned an empty response")
    return json.loads(raw.split(b"\n", 1)[0].decode("utf-8"))


def wait_until_ready(
    process: subprocess.Popen[str],
    socket_path: Path,
    token_path: Path,
) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            detail = (stderr or stdout).strip()[:500]
            raise RuntimeError(
                f"isolated daemon exited early ({process.returncode}): {detail}"
            )
        if socket_path.exists() and token_path.exists():
            token = token_path.read_text(encoding="utf-8").strip()
            try:
                response = request(socket_path, token, {"op": "ping"})
            except (OSError, ValueError, json.JSONDecodeError):
                time.sleep(0.05)
                continue
            if response.get("ok") and response.get("pong"):
                return token
        time.sleep(0.05)
    raise RuntimeError("isolated daemon did not become ready")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dh-daemon-example-") as temp_dir:
        temp_root = Path(temp_dir)
        socket_path = temp_root / "daemon.sock"
        token_path = temp_root / "daemon.token"

        env = os.environ.copy()
        env["DH_SOCKET"] = str(socket_path)
        env["DH_TOKEN_PATH"] = str(token_path)
        env["DH_AUDIT_LOG"] = str(temp_root / "audit.jsonl")
        env["DH_NO_DAEMON"] = "1"
        env["DH_PRESENCE"] = "0"
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(ROOT / "src") + (
            os.pathsep + old_pythonpath if old_pythonpath else ""
        )

        process = subprocess.Popen(
            [harness_python(), "-m", "desktop_harness.run", "daemon", "serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        token = ""
        try:
            token = wait_until_ready(process, socket_path, token_path)
            response = request(
                socket_path,
                token,
                {"op": "exec", "code": "print(6 * 7)"},
            )
            if not response.get("ok"):
                raise RuntimeError("isolated daemon execution failed")
            output = str(response.get("stdout") or "").strip()
            if output != "42":
                raise RuntimeError(f"unexpected daemon result: {output!r}")

            summary = {
                "daemon_roundtrip": "PASS",
                "exec_result": 42,
                "network": "not_used",
            }
            print(RESULT_PREFIX + json.dumps(summary, sort_keys=True))
            print("PASS: isolated daemon round-trip completed")
            return 0
        finally:
            if process.poll() is None:
                try:
                    if token:
                        request(socket_path, token, {"op": "quit"})
                except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
