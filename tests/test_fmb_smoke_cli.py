"""Offline smoke tests for desktop-harness modules and CLI entry points."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "desktop_harness",
    "desktop_harness.admin",
    "desktop_harness.ax",
    "desktop_harness.capture",
    "desktop_harness.daemon",
    "desktop_harness.demo",
    "desktop_harness.helpers",
    "desktop_harness.input",
    "desktop_harness.presence",
    "desktop_harness.run",
    "desktop_harness.safety",
    "desktop_harness.selftest",
    "desktop_harness.voice_tools",
    "desktop_harness.windows",
)


def _require_macos_frameworks() -> None:
    if sys.platform != "darwin":
        pytest.skip(
            "完整模組匯入與最小腳本執行需 macOS 的 PyObjC frameworks "
            "(Quartz、AppKit、ApplicationServices)。"
        )


def _offline_env(tmp_path: Path) -> dict[str, str]:
    """Provide isolated paths and avoid inheriting API credentials."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DH_NO_DAEMON": "1",
        "DH_PRESENCE": "0",
        "DH_AUDIT_LOG": str(tmp_path / "audit.jsonl"),
        "DH_SOCKET": str(tmp_path / "daemon.sock"),
        "DH_TOKEN_PATH": str(tmp_path / "daemon.token"),
        "TMPDIR": str(tmp_path),
    }
    # Required by some Windows Python installations; harmless elsewhere.
    for name in ("SYSTEMROOT", "WINDIR"):
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _run_cli(
    tmp_path: Path,
    *args: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "desktop_harness.run", *args],
        cwd=REPO_ROOT,
        env=_offline_env(tmp_path),
        input=input_text,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_all_package_modules_import_offline(tmp_path: Path) -> None:
    _require_macos_frameworks()

    code = (
        "import importlib\n"
        f"modules = {MODULES!r}\n"
        "for module in modules:\n"
        "    importlib.import_module(module)\n"
        "print('FMB_SMOKE_IMPORTS_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=_offline_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FMB_SMOKE_IMPORTS_OK" in result.stdout


def test_cli_help_exits_successfully_offline(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "--help")

    output = (result.stdout + result.stderr).lower()
    assert result.returncode == 0, output
    # This CLI prints a custom command overview rather than argparse "usage".
    assert "desktop-harness --version" in output


def test_cli_version_reports_package_version_offline(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "--version")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "0.4.2" in (result.stdout + result.stderr)


def test_cli_executes_minimal_stdin_input_offline(tmp_path: Path) -> None:
    _require_macos_frameworks()

    result = _run_cli(
        tmp_path,
        input_text='print("FMB_SMOKE_INPUT_OK")\n',
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FMB_SMOKE_INPUT_OK" in result.stdout
    assert not (tmp_path / "daemon.sock").exists()
    assert not (tmp_path / "daemon.token").exists()
