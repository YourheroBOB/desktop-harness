"""Integration and End-to-End tests for desktop-harness.

Covers:
1. CLI / packaging entry-point integration (file I/O, skill payload).
2. CLI stdin execution E2E (success, syntax error, runtime exception) — macOS only.
3. CLI subcommands (`skill`, `daemon status`) — macOS only.
4. File I/O: audit log creation, append and JSONL formatting in isolated temp path.
5. Safety gates & error paths (sensitive apps, DH_ALLOW_SENSITIVE override, safe mode).
6. Voice tools & scripts offline execution / error paths — macOS only.
7. Daemon socket protocol & token/absence error paths in an isolated sandbox.

Environment notes:
- Tests that need pyobjc (Quartz / AppKit / ApplicationServices) are skipped on
  non-macOS hosts or when the macOS frameworks are missing, because the core
  modules import them at module scope.
- No test touches the network, the user's real daemon, or paths outside
  ``tmp_path``. Fake credentials are always the literal ``FAKE_VALUE_FOR_TEST``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure repo `src` directory is on sys.path before importing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# `safety` is pure stdlib — safe to import on every platform.
from desktop_harness import safety


def _pyobjc_available() -> bool:
    """True only when the macOS automation frameworks can actually be imported."""
    if sys.platform != "darwin":
        return False
    try:
        import AppKit  # noqa: F401
        import Quartz  # noqa: F401
        from ApplicationServices import AXIsProcessTrusted  # noqa: F401
    except Exception:
        return False
    return True


HAS_PYOBJC = _pyobjc_available()

requires_pyobjc = pytest.mark.skipif(
    not HAS_PYOBJC,
    reason=(
        "macOS pyobjc frameworks (Quartz/AppKit/ApplicationServices) not available; "
        "desktop_harness.helpers/ax import them at module scope"
    ),
)


def _daemon_module():
    """Import desktop_harness.daemon, or return None if it cannot be imported."""
    try:
        from desktop_harness import daemon as daemon_mod
    except Exception:
        return None
    return daemon_mod


# Errors `daemon.client_request()` currently lets escape when nothing is
# listening (it calls `socket.connect()` with no guard around it). The
# graceful-degradation contract lives in `daemon.is_running()` and the
# `run.py` routing layer, not in `client_request()` itself.
# Tracked in docs/fmb-perf/findings-daemon.md (DAEMON-2 / DAEMON-4 family).
NO_DAEMON_SOCKET_ERRORS = (
    FileNotFoundError,
    ConnectionRefusedError,
    ConnectionResetError,
    PermissionError,
    TimeoutError,
    OSError,
)


@pytest.fixture
def isolated_env(tmp_path: Path) -> dict[str, str]:
    """Provide a sandboxed environment dictionary isolating all harness I/O."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    env["DH_NO_DAEMON"] = "1"
    env["DH_AUDIT_LOG"] = str(tmp_path / "audit.jsonl")
    env["DH_SOCKET"] = str(tmp_path / "daemon.sock")
    env["DH_TOKEN_PATH"] = str(tmp_path / "daemon.token")
    env["DH_SAFE"] = "1"
    env.pop("DH_ALLOW_SENSITIVE", None)
    return env


class TestPackagingAndDocsIo:
    """Platform-independent file I/O / packaging integration checks."""

    def test_pyproject_declares_console_script(self):
        """pyproject must expose the `desktop-harness` console entry point."""
        try:
            import tomllib
        except ModuleNotFoundError:  # Python < 3.11
            pytest.skip("tomllib not available in this interpreter")

        pyproject = REPO_ROOT / "pyproject.toml"
        assert pyproject.exists(), "pyproject.toml missing from repo root"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        scripts = data.get("project", {}).get("scripts", {})
        assert scripts.get("desktop-harness") == "desktop_harness.run:main"

    def test_skill_payload_present_and_packaged(self):
        """Root SKILL.md and the packaged data copy must both exist and be non-empty."""
        root_skill = REPO_ROOT / "SKILL.md"
        packaged_skill = SRC_DIR / "desktop_harness" / "data" / "SKILL.md"

        assert root_skill.exists(), "root SKILL.md missing"
        assert packaged_skill.exists(), "packaged data/SKILL.md missing"

        root_text = root_skill.read_text(encoding="utf-8")
        packaged_text = packaged_skill.read_text(encoding="utf-8")
        assert "name: desktop-harness" in root_text
        assert packaged_text.strip(), "packaged SKILL.md is empty"

    def test_run_module_source_is_parseable(self):
        """run.py must be syntactically valid without importing pyobjc."""
        import ast

        run_py = SRC_DIR / "desktop_harness" / "run.py"
        assert run_py.exists(), "src/desktop_harness/run.py missing"
        source = run_py.read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert "main" in funcs, "run.py does not define main()"


@requires_pyobjc
class TestCliExecutionE2E:
    """End-to-End integration tests invoking desktop-harness CLI (macOS)."""

    def test_cli_stdin_exec_success(self, isolated_env: dict[str, str]):
        """CLI should read Python code from stdin and execute successfully."""
        script = 'print("INTEGRATION_CLI_OUTPUT_OK")\n'
        result = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run"],
            input=script,
            text=True,
            capture_output=True,
            env=isolated_env,
            timeout=60,
        )
        assert result.returncode == 0, f"CLI execution failed: {result.stderr}"
        assert "INTEGRATION_CLI_OUTPUT_OK" in result.stdout

    def test_cli_stdin_exec_syntax_error(self, isolated_env: dict[str, str]):
        """CLI should report non-zero returncode on syntax error."""
        broken_script = "def unclosed_syntax_test(:\n"
        result = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run"],
            input=broken_script,
            text=True,
            capture_output=True,
            env=isolated_env,
            timeout=60,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "SyntaxError" in combined or "error" in combined.lower()

    def test_cli_stdin_exec_runtime_exception(self, isolated_env: dict[str, str]):
        """CLI should report non-zero returncode on runtime exception."""
        exception_script = 'raise RuntimeError("CONTROLLED_TEST_EXCEPTION")\n'
        result = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run"],
            input=exception_script,
            text=True,
            capture_output=True,
            env=isolated_env,
            timeout=60,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "CONTROLLED_TEST_EXCEPTION" in combined

    def test_cli_subcommand_skill(self, isolated_env: dict[str, str]):
        """`desktop-harness skill` should output the SKILL.md payload."""
        result = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run", "skill"],
            text=True,
            capture_output=True,
            env=isolated_env,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "desktop-harness" in result.stdout
        assert "Accessibility" in result.stdout or "Grok Build" in result.stdout

    def test_cli_daemon_status_when_stopped(self, isolated_env: dict[str, str]):
        """`daemon status` against an isolated socket must report not-running."""
        result = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run", "daemon", "status"],
            text=True,
            capture_output=True,
            env=isolated_env,
            timeout=60,
        )
        combined = (result.stdout + result.stderr).lower()
        assert (
            "not running" in combined
            or "stopped" in combined
            or result.returncode != 0
        )


class TestFileIoAndSafety:
    """Integration tests for audit log file I/O and safety gates (all platforms)."""

    def test_audit_log_io_creation_and_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """audit() writes JSONL into an isolated temp directory, auto-creating parents."""
        log_file = tmp_path / "test_audit" / "audit.jsonl"
        monkeypatch.setattr(safety, "_AUDIT", log_file)

        safety.audit("test_event_1", {"key1": "val1", "pid": 1234})
        safety.audit("test_event_2", {"key2": "val2", "flag": True})

        assert log_file.exists(), "Audit file should be created automatically"
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1["event"] == "test_event_1"
        assert entry1["detail"] == {"key1": "val1", "pid": 1234}
        assert isinstance(entry1["ts"], (int, float))

        entry2 = json.loads(lines[1])
        assert entry2["event"] == "test_event_2"
        assert entry2["detail"] == {"key2": "val2", "flag": True}

    def test_audit_log_swallows_io_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """audit() must never raise even when the log path is unusable."""
        blocked_parent = tmp_path / "not_a_directory"
        blocked_parent.write_text("occupied", encoding="utf-8")
        monkeypatch.setattr(safety, "_AUDIT", blocked_parent / "audit.jsonl")

        # Must not raise (safety.audit is best-effort by design).
        safety.audit("should_not_crash", {"value": "FAKE_VALUE_FOR_TEST"})
        assert blocked_parent.is_file()

    def test_safety_check_app_allowed_blocks_sensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Sensitive apps must raise PermissionError by default."""
        monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
        sensitive_samples = [
            ("1Password", ""),
            ("Bitwarden", "com.bitwarden.desktop"),
            ("Keychain Access", "com.apple.keychainaccess"),
            ("LastPass", ""),
            ("KeePassXC", "org.keepassxc.keepassxc"),
            ("Personal Bank Vault", ""),
        ]
        for name, bundle_id in sensitive_samples:
            with pytest.raises(PermissionError) as exc_info:
                safety.check_app_allowed(name, bundle_id)
            assert "refusing to control sensitive app" in str(exc_info.value)

    def test_safety_check_app_allowed_permits_safe(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Safe non-sensitive apps should not raise exceptions."""
        monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
        safe_samples = [
            ("TextEdit", "com.apple.TextEdit"),
            ("Finder", "com.apple.finder"),
            ("Calculator", "com.apple.calculator"),
            ("Terminal", "com.apple.Terminal"),
        ]
        for name, bundle_id in safe_samples:
            safety.check_app_allowed(name, bundle_id)

    def test_safety_allow_sensitive_override(self, monkeypatch: pytest.MonkeyPatch):
        """DH_ALLOW_SENSITIVE=1 must explicitly lift the sensitive-app gate."""
        monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
        safety.check_app_allowed("1Password", "com.agilebits.onepassword")
        safety.check_app_allowed("Bitwarden", "")

    def test_safety_check_helper_allowed_blocks_high_risk(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """High-risk helper names must be blocked under DH_SAFE=1."""
        monkeypatch.setenv("DH_SAFE", "1")
        monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)

        for blocked in ("run_shell", "shell", "osascript_raw"):
            with pytest.raises(PermissionError) as exc:
                safety.check_helper_allowed(blocked)
            assert "blocked in safe mode" in str(exc.value)

        # Non-blocked helper should pass.
        safety.check_helper_allowed("click_text")


@requires_pyobjc
class TestVoiceToolsOfflineAndErrorPaths:
    """Voice tool schemas, dispatching and error paths — never touches the network."""

    def test_voice_tools_definitions_structure(self):
        """TOOL_DEFINITIONS must match the expected function-calling schema."""
        from desktop_harness.voice_tools import TOOL_DEFINITIONS

        assert isinstance(TOOL_DEFINITIONS, list)
        assert len(TOOL_DEFINITIONS) > 0
        names = {t["name"] for t in TOOL_DEFINITIONS}
        expected = {
            "list_apps",
            "open_app",
            "click_text",
            "type_text",
            "hotkey",
            "click_xy",
        }
        assert expected.issubset(names)

        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert tool["parameters"].get("type") == "object"

    def test_voice_tools_execute_unknown_tool(self):
        """Unknown tool names must return an error string, not raise."""
        from desktop_harness.voice_tools import execute as voice_execute

        out = voice_execute("non_existent_tool_xyz", {})
        assert "unknown tool" in out.lower()

    def test_voice_tools_execute_invalid_json_arguments(self):
        """Malformed JSON arguments must return a parse error string, not crash."""
        from desktop_harness.voice_tools import execute as voice_execute

        out = voice_execute("list_apps", "{invalid_json_format")
        assert "parse error" in out.lower() or "error" in out.lower()

    def test_voice_tools_dry_run_dispatch(self):
        """dry_run dispatch is safe and never performs real input."""
        from desktop_harness.voice_tools import execute as voice_execute

        out_pos = voice_execute("mouse_pos", {}, dry_run=True)
        assert isinstance(out_pos, str)

        out_click = voice_execute("click_xy", {"x": 100, "y": 200}, dry_run=True)
        assert isinstance(out_click, str)
        assert "dry-run" in out_click.lower() or "click" in out_click.lower()

    def test_voice_session_script_missing_key_behavior(self, isolated_env: dict):
        """voice_session.py must exit 2 with a clear message when no API key is set."""
        script_path = REPO_ROOT / "scripts" / "voice_session.py"
        if not script_path.exists():
            pytest.skip("scripts/voice_session.py not present")

        env = dict(isolated_env)
        env["XAI_API_KEY"] = ""
        result = subprocess.run(
            [sys.executable, str(script_path)],
            text=True,
            capture_output=True,
            env=env,
            timeout=60,
        )
        assert result.returncode == 2
        assert "Missing XAI_API_KEY" in result.stderr
        # Never echo a fake key value back into the transcript.
        assert "FAKE_VALUE_FOR_TEST" not in result.stdout

    def test_voice_session_script_list_tools_is_offline(self, isolated_env: dict):
        """--list-tools must print the tool surface and exit 0 without a key."""
        script_path = REPO_ROOT / "scripts" / "voice_session.py"
        if not script_path.exists():
            pytest.skip("scripts/voice_session.py not present")

        env = dict(isolated_env)
        env["XAI_API_KEY"] = ""
        result = subprocess.run(
            [sys.executable, str(script_path), "--list-tools"],
            text=True,
            capture_output=True,
            env=env,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "list_apps" in result.stdout


class TestDaemonIsolatedProtocol:
    """Daemon absence / auth error paths, isolated via tmp_path.

    No daemon is ever started here and every socket/token path points into
    ``tmp_path``, so a developer's real warm daemon is never touched.
    """

    def test_daemon_is_running_false_when_socket_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """`is_running()` is the documented guard: False when no socket exists."""
        daemon = _daemon_module()
        if daemon is None:
            pytest.skip("desktop_harness.daemon not importable in this environment")
        if not hasattr(daemon, "SOCKET_PATH"):
            pytest.skip("daemon module does not expose SOCKET_PATH")

        absent_sock = tmp_path / "absent.sock"
        monkeypatch.setattr(daemon, "SOCKET_PATH", absent_sock)
        monkeypatch.setenv("DH_SOCKET", str(absent_sock))
        monkeypatch.setenv("DH_TOKEN_PATH", str(tmp_path / "absent.token"))

        assert absent_sock.exists() is False
        assert daemon.is_running() is False

    @pytest.mark.xfail(
        raises=NO_DAEMON_SOCKET_ERRORS,
        strict=False,
        reason=(
            "product gap (cannot fix here): daemon.client_request() calls "
            "socket.connect() unguarded, so with no daemon it raises "
            "FileNotFoundError/ConnectionRefusedError instead of returning "
            "{'ok': False}. Graceful fallback currently lives in "
            "is_running()/run.py, not in client_request(). "
            "See docs/fmb-perf/findings-daemon.md (DAEMON-2/DAEMON-4)."
        ),
    )
    def test_daemon_client_request_returns_error_dict_when_no_server(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Desired contract: client_request degrades to None or {'ok': False}."""
        daemon = _daemon_module()
        if daemon is None:
            pytest.skip("desktop_harness.daemon not importable in this environment")
        if not hasattr(daemon, "client_request"):
            pytest.skip("daemon module does not expose client_request")

        absent_sock = tmp_path / "absent.sock"
        monkeypatch.setattr(
            daemon, "SOCKET_PATH", absent_sock, raising=False
        )
        monkeypatch.setenv("DH_SOCKET", str(absent_sock))
        monkeypatch.setenv("DH_TOKEN_PATH", str(tmp_path / "absent.token"))

        resp = daemon.client_request({"op": "ping"}, timeout=0.1)
        assert resp is None or resp.get("ok") is False

    def test_daemon_exec_cannot_run_without_live_daemon(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """No live daemon ⇒ no arbitrary code execution. Sentinel must stay absent."""
        daemon = _daemon_module()
        if daemon is None:
            pytest.skip("desktop_harness.daemon not importable in this environment")
        if not hasattr(daemon, "client_request"):
            pytest.skip("daemon module does not expose client_request")

        absent_sock = tmp_path / "no-daemon.sock"
        sentinel = tmp_path / "executed.txt"
        monkeypatch.setattr(
            daemon, "SOCKET_PATH", absent_sock, raising=False
        )
        monkeypatch.setenv("DH_SOCKET", str(absent_sock))
        monkeypatch.setenv("DH_TOKEN_PATH", str(tmp_path / "no-daemon.token"))

        payload = {
            "op": "exec",
            "code": f"open({str(sentinel)!r}, 'w').write('FAKE_VALUE_FOR_TEST')",
        }
        resp = None
        try:
            resp = daemon.client_request(payload, timeout=0.1)
        except NO_DAEMON_SOCKET_ERRORS:
            # Expected today: the raw OS error escapes. What matters for this
            # safety test is that nothing executed on the other side.
            pass

        assert not sentinel.exists(), "code executed despite no live daemon"
        assert resp is None or resp.get("ok") is False
