"""整合與端到端情境測試 (CLI 執行、檔案 I/O、安全防護與錯誤路徑).

涵蓋範圍:
1. CLI 執行與端到端參數驗證 (--version, skill 命令, 錯誤 flag, stdin 執行)
2. 檔案 I/O 與審計日誌 (audit.jsonl 自動建檔、多筆 JSONL 附加寫入、內容驗證)
3. 安全模組防護與錯誤路徑 (敏感 App 攔截、安全模式高風險 Helper 封鎖、前台敏感 App 攔截)
4. Warm Daemon 通訊協議、Token I/O 與錯誤處理 (Token 0600 權限、Socket 通訊、未授權拒絕、無效 JSON)
5. 螢幕截圖安全前置檢查 (在觸發 I/O 前阻擋敏感 App)
6. Voice Tools 分派、Dry-run 與無效參數錯誤路徑
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

# 確保在未安裝 package 情況下可載入 src/desktop_harness
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import desktop_harness
from desktop_harness import daemon, safety

# CLI commands that load the full runtime, screenshot checks, and voice-tool
# dispatch require the macOS PyObjC frameworks. Keep platform-independent
# audit, safety, and daemon protocol tests runnable on Linux.
try:
    HAS_PYOBJC = all(
        importlib.util.find_spec(module) is not None
        for module in ("ApplicationServices", "Quartz", "AppKit")
    )
except (ImportError, ValueError):
    HAS_PYOBJC = False

if HAS_PYOBJC:
    try:
        from desktop_harness import voice_tools
    except ImportError:
        HAS_PYOBJC = False
        voice_tools = None
else:
    voice_tools = None


@unittest.skipUnless(HAS_PYOBJC, "requires macOS PyObjC frameworks")
class TestCLIE2EIntegration(unittest.TestCase):
    """CLI 執行整合測試 (命令列旗標、端到端子命令、標準輸入)."""

    def setUp(self):
        self.env = {
            **os.environ,
            "PYTHONPATH": str(SRC_DIR),
            "DH_NO_DAEMON": "1",
        }

    def test_cli_version_flag(self):
        """測試 desktop-harness --version 執行並比對版本號."""
        res = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run", "--version"],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=15,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"CLI --version failed: stderr={res.stderr!r}",
        )
        self.assertIn(desktop_harness.__version__, res.stdout)

    def test_cli_skill_output(self):
        """測試 desktop-harness skill 命令正確輸出 SKILL.md 規格內容."""
        res = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run", "skill"],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=15,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"CLI skill command failed: stderr={res.stderr!r}",
        )
        self.assertIn("# desktop-harness", res.stdout)
        self.assertIn("Grok Build", res.stdout)
        self.assertIn("click_text", res.stdout)

    def test_cli_invalid_flag_error_path(self):
        """測試 CLI 傳入未定義的命令時之錯誤處理路徑."""
        res = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run", "--invalid-nonexistent-flag-xyz"],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=15,
        )
        # 未知旗標應以非 0 結束或印出使用說明/警告
        self.assertTrue(
            res.returncode != 0 or "Usage" in res.stderr or "Usage" in res.stdout or "invalid" in res.stderr.lower(),
            f"Expected error for invalid flag, got returncode={res.returncode}",
        )

    def test_cli_stdin_code_exec(self):
        """測試透過 stdin 餵入 Python 腳本由 CLI 執行 (DH_NO_DAEMON 模式)."""
        test_marker = "DH_CLI_E2E_STDIN_VERIFIED_OK"
        code = f"import sys; sys.stdout.write('{test_marker}\\n')\n"
        res = subprocess.run(
            [sys.executable, "-m", "desktop_harness.run"],
            input=code,
            capture_output=True,
            text=True,
            env=self.env,
            timeout=15,
        )
        self.assertEqual(res.returncode, 0, f"Failed stdin run: {res.stderr}")
        self.assertIn(test_marker, res.stdout)


class TestSafetyAuditFileIOIntegration(unittest.TestCase):
    """檔案 I/O 與安全審計日誌整合測試."""

    def test_audit_log_file_io_creation_and_append(self):
        """測試 audit() 寫入自訂路徑，驗證目錄自動創建與 JSONL 格式合法性."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            audit_path = Path(tmp_dir) / "sub" / "dir" / "audit.jsonl"
            with mock.patch.object(safety, "_AUDIT", audit_path):
                # 寫入第一筆事件
                safety.audit("test_init", {"step": 1, "value": "FIRST"})
                self.assertTrue(audit_path.exists(), "audit log file must be created")

                # 寫入第二筆事件 (包含 Unicode 與特殊字元)
                safety.audit("test_action", {"step": 2, "value": "中文測試與符號!@#$%"})

            lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 2)

            rec1 = json.loads(lines[0])
            self.assertEqual(rec1["event"], "test_init")
            self.assertEqual(rec1["detail"]["value"], "FIRST")
            self.assertIsInstance(rec1["ts"], float)

            rec2 = json.loads(lines[1])
            self.assertEqual(rec2["event"], "test_action")
            self.assertEqual(rec2["detail"]["value"], "中文測試與符號!@#$%")

    def test_sensitive_app_blocked_error_paths(self):
        """測試安全門檻阻擋敏感應用程式 (1Password, Bitwarden, Keychain 等)."""
        blocked_apps = [
            ("1Password", "com.agilebits.onepassword7"),
            ("Bitwarden", "com.bitwarden.desktop"),
            ("Keychain Access", "com.apple.keychainaccess"),
            ("NordPass", "com.nordpass.osx"),
            ("My Bank App", "com.bank.secure"),
            ("Crypto Wallet", "com.wallet.keys"),
        ]

        with mock.patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": ""}, clear=False):
            self.assertFalse(safety.allow_sensitive())
            for name, bundle in blocked_apps:
                with self.assertRaises(PermissionError, msg=f"Should block {name}") as ctx:
                    safety.check_app_allowed(name, bundle)
                self.assertIn("refusing to control sensitive app", str(ctx.exception))

    def test_sensitive_app_allowed_when_override_env_set(self):
        """測試當 DH_ALLOW_SENSITIVE=1 時安全限制得以解除."""
        for truthy in ("1", "true", "yes", "TRUE"):
            with mock.patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": truthy}, clear=False):
                self.assertTrue(safety.allow_sensitive())
                try:
                    safety.check_app_allowed("1Password", "com.agilebits.onepassword7")
                except PermissionError:
                    self.fail(f"DH_ALLOW_SENSITIVE={truthy} should not raise PermissionError")

    def test_safe_mode_blocks_high_risk_helpers(self):
        """測試 safe_mode 攔截高風險 helper 呼叫."""
        high_risk = ["run_shell", "shell", "osascript_raw"]
        with mock.patch.dict(os.environ, {"DH_SAFE": "1", "DH_ALLOW_SENSITIVE": ""}, clear=False):
            for h in high_risk:
                with self.assertRaises(PermissionError) as ctx:
                    safety.check_helper_allowed(h)
                self.assertIn("blocked in safe mode", str(ctx.exception))

            # 普通 helper 不應被擋
            safety.check_helper_allowed("click_text")
            safety.check_helper_allowed("labels")

    @unittest.skipUnless(HAS_PYOBJC, "requires macOS PyObjC frameworks")
    def test_check_frontmost_allowed_error_path(self):
        """測試當前台應用程式為敏感應用時，check_frontmost_allowed 拋出 PermissionError."""
        mock_front = {
            "name": "1Password",
            "bundle_id": "com.agilebits.onepassword7",
            "pid": 12345,
            "active": True,
        }
        with mock.patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": ""}, clear=False):
            with mock.patch("desktop_harness.windows.frontmost_app", return_value=mock_front):
                with self.assertRaises(PermissionError):
                    safety.check_frontmost_allowed()

        # 若為普通應用則不拋出異常
        safe_front = {
            "name": "TextEdit",
            "bundle_id": "com.apple.TextEdit",
            "pid": 54321,
            "active": True,
        }
        with mock.patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": ""}, clear=False):
            with mock.patch("desktop_harness.windows.frontmost_app", return_value=safe_front):
                safety.check_frontmost_allowed()


class TestDaemonIPCTokenIntegration(unittest.TestCase):
    """Daemon 通訊、Token 權限與 IPC 錯誤路徑測試."""

    def test_daemon_token_file_io_and_permissions(self):
        """測試 _write_token 與 _read_token 的檔案 I/O 及 0600 權限設定."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            token_file = Path(tmp_dir) / "daemon.token"
            with mock.patch.object(daemon, "TOKEN_PATH", token_file):
                # 初始狀態不存在
                self.assertIsNone(daemon._read_token())

                tok = daemon._write_token()
                self.assertTrue(token_file.exists())
                self.assertEqual(len(tok), 48)  # token_hex(24) -> 48 chars
                self.assertEqual(daemon._read_token(), tok)

                # 檢驗 POSIX 權限 0o600
                if os.name == "posix":
                    stat_mode = token_file.stat().st_mode & 0o777
                    self.assertEqual(stat_mode, 0o600)

    def test_daemon_is_running_when_socket_missing(self):
        """測試當 socket 檔不存在時 is_running 返回 False."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            non_existent = Path(tmp_dir) / "missing.sock"
            with mock.patch.object(daemon, "SOCKET_PATH", non_existent):
                self.assertFalse(daemon.is_running())

    def test_daemon_ipc_roundtrip_and_error_paths(self):
        """以真實 Unix Socket 測試 Daemon IPC 協議、Token 驗證與錯誤處理路徑."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sock_path = Path(tmp_dir) / "test_daemon.sock"
            token_path = Path(tmp_dir) / "test_daemon.token"

            # 準備 Token
            expected_token = "FAKE_VALUE_FOR_TEST_TOKEN_1234567890abcdef"
            token_path.write_text(expected_token)

            stop_event = threading.Event()

            def mock_server():
                srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                srv.bind(str(sock_path))
                srv.listen(5)
                srv.settimeout(2.0)
                try:
                    while not stop_event.is_set():
                        try:
                            conn, _ = srv.accept()
                        except socket.timeout:
                            continue
                        with conn:
                            buf = b""
                            while b"\n" not in buf:
                                chunk = conn.recv(1024)
                                if not chunk:
                                    break
                                buf += chunk
                            if not buf:
                                continue
                            try:
                                req = json.loads(buf.decode())
                            except json.JSONDecodeError as err:
                                conn.sendall((json.dumps({"ok": False, "error": str(err)}) + "\n").encode())
                                continue

                            # 檢查 Token
                            if req.get("token") != expected_token:
                                conn.sendall(b'{"ok":false,"error":"unauthorized (bad or missing token)"}\n')
                                continue

                            op = req.get("op")
                            if op == "ping":
                                conn.sendall(b'{"ok":true,"pong":true}\n')
                            elif op == "echo":
                                conn.sendall((json.dumps({"ok": True, "echo": req.get("msg")}) + "\n").encode())
                            elif op == "quit":
                                conn.sendall(b'{"ok":true}\n')
                                break
                            else:
                                conn.sendall((json.dumps({"ok": False, "error": f"unknown op {op}"}) + "\n").encode())
                finally:
                    srv.close()

            server_thread = threading.Thread(target=mock_server, daemon=True)
            server_thread.start()
            time.sleep(0.1)  # 等候 socket bind

            with mock.patch.object(daemon, "SOCKET_PATH", sock_path), \
                 mock.patch.object(daemon, "TOKEN_PATH", token_path):

                # 1. 正常 Token -> ping
                ping_res = daemon.client_request({"op": "ping"}, timeout=2.0)
                self.assertTrue(ping_res.get("ok"))
                self.assertTrue(ping_res.get("pong"))

                # 2. 正常 Token -> 自訂 echo
                echo_res = daemon.client_request({"op": "echo", "msg": "HELLO_DAEMON"}, timeout=2.0)
                self.assertTrue(echo_res.get("ok"))
                self.assertEqual(echo_res.get("echo"), "HELLO_DAEMON")

                # 3. 錯誤 Token 錯誤路徑
                bad_token_res = daemon.client_request(
                    {"op": "ping", "token": "FAKE_VALUE_FOR_TEST_WRONG"},
                    timeout=2.0,
                )
                self.assertFalse(bad_token_res.get("ok"))
                self.assertIn("unauthorized", bad_token_res.get("error", ""))

                # 4. 未知 op 錯誤路徑
                unknown_op_res = daemon.client_request({"op": "invalid_operation"}, timeout=2.0)
                self.assertFalse(unknown_op_res.get("ok"))
                self.assertIn("unknown op", unknown_op_res.get("error", ""))

                # 5. 送出毀損 JSON 錯誤路徑
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as raw_sock:
                    raw_sock.connect(str(sock_path))
                    raw_sock.sendall(b"{bad json text\n")
                    raw_reply = raw_sock.recv(1024)
                    raw_parsed = json.loads(raw_reply.decode())
                    self.assertFalse(raw_parsed.get("ok"))

                # 6. quit op
                quit_res = daemon.client_request({"op": "quit"}, timeout=2.0)
                self.assertTrue(quit_res.get("ok"))

            stop_event.set()
            server_thread.join(timeout=2.0)


@unittest.skipUnless(HAS_PYOBJC, "requires macOS PyObjC frameworks")
class TestCaptureSafetyIntegration(unittest.TestCase):
    """螢幕截圖模組安全攔截測試 (在進行真實 I/O 截圖前阻擋)."""

    def test_screenshot_sensitive_app_prevented_before_io(self):
        """測試 screenshot(app='1Password') 觸發安全檢查並拒絕截圖."""
        from desktop_harness import capture

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_png = Path(tmp_dir) / "should_not_exist.png"
            with mock.patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": ""}, clear=False):
                with self.assertRaises(PermissionError):
                    capture.screenshot(app="1Password", path=out_png)

            self.assertFalse(out_png.exists(), "No screenshot file should be written for sensitive app")

    def test_screenshot_frontmost_sensitive_prevented(self):
        """測試無指定 app 時，若 frontmost 為敏感 app 則攔截截圖."""
        from desktop_harness import capture

        mock_front = {"name": "Bitwarden", "bundle_id": "com.bitwarden.desktop"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_png = Path(tmp_dir) / "front_leak.png"
            with mock.patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": ""}, clear=False):
                with mock.patch("desktop_harness.windows.frontmost_app", return_value=mock_front):
                    with self.assertRaises(PermissionError):
                        capture.screenshot(app=None, path=out_png)

            self.assertFalse(out_png.exists())


@unittest.skipUnless(HAS_PYOBJC, "requires macOS PyObjC frameworks")
class TestVoiceToolsE2EIntegration(unittest.TestCase):
    """Voice 工具端到端分派、Dry-run 與參數錯誤處理測試."""

    def test_all_voice_tools_dry_run(self):
        """測試所有在 TOOL_DEFINITIONS 中的工具皆可於 dry_run 模式下正常執行."""
        tool_names = [t["name"] for t in voice_tools.TOOL_DEFINITIONS]
        self.assertGreaterEqual(len(tool_names), 8)

        sample_args = {
            "open_app": {"name": "TextEdit"},
            "screen_labels": {"limit": 10},
            "click_text": {"text": "OK"},
            "type_text": {"text": "hello"},
            "hotkey": {"keys": ["cmd", "s"]},
            "move_mouse": {"x": 100, "y": 200},
            "click_xy": {"x": 150, "y": 250},
        }

        for name in tool_names:
            args = sample_args.get(name, {})
            out_raw = voice_tools.execute(name, args, dry_run=True)
            res = json.loads(out_raw)
            self.assertTrue(res.get("ok"), f"Tool {name} dry_run should be ok")
            self.assertEqual(res["result"]["tool"], name)
            self.assertTrue(res["result"]["dry_run"])

    def test_voice_tools_invalid_json_arguments_error_path(self):
        """測試當傳入非合法 JSON 字串時的回應錯誤處理."""
        bad_json = "{this is not json,"
        out_raw = voice_tools.execute("open_app", bad_json, dry_run=False)
        res = json.loads(out_raw)
        self.assertFalse(res.get("ok"))
        self.assertIn("invalid arguments JSON", res.get("error", ""))

    def test_voice_tools_unknown_tool_error_path(self):
        """測試未知 tool 名稱時的錯誤處理."""
        out_raw = voice_tools.execute("non_existent_tool_xyz", {}, dry_run=False)
        res = json.loads(out_raw)
        self.assertFalse(res.get("ok"))
        self.assertIn("unknown tool", res.get("error", ""))

    def test_voice_tools_handlers_mapping(self):
        """測試 handlers() 產生的回調字典映射正確."""
        handlers = voice_tools.handlers(dry_run=True)
        self.assertIn("open_app", handlers)
        self.assertIn("type_text", handlers)

        fn = handlers["open_app"]
        res = json.loads(fn(name="Safari"))
        self.assertTrue(res.get("ok"))
        self.assertEqual(res["result"]["arguments"]["name"], "Safari")


if __name__ == "__main__":
    unittest.main(verbosity=2)
