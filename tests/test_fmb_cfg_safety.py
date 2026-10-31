"""離線測試 desktop-harness 的安全設定與環境變數處理。"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


# 讓測試可直接從 src-layout 的工作樹執行，不依賴已安裝的套件。
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from desktop_harness import safety  # noqa: E402


def test_safety_settings_use_secure_defaults(monkeypatch):
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    monkeypatch.delenv("DH_SAFE", raising=False)

    assert safety.allow_sensitive() is False
    assert safety.safe_mode() is True


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_allow_sensitive_accepts_documented_truthy_values(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)

    assert safety.allow_sensitive() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "enabled", ""])
def test_invalid_or_false_allow_sensitive_values_remain_disabled(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)

    assert safety.allow_sensitive() is False


@pytest.mark.parametrize("value", ["0", "false", "no", "FALSE"])
def test_safe_mode_can_be_disabled_with_documented_values(monkeypatch, value):
    monkeypatch.setenv("DH_SAFE", value)

    assert safety.safe_mode() is False


@pytest.mark.parametrize("value", ["", "enabled", "unexpected"])
def test_invalid_safe_mode_values_keep_safe_default(monkeypatch, value):
    monkeypatch.setenv("DH_SAFE", value)

    assert safety.safe_mode() is True


def test_sensitive_app_is_blocked_unless_explicitly_allowed(monkeypatch):
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)

    with pytest.raises(PermissionError):
        safety.check_app_allowed("FAKE_VALUE_FOR_TEST-keychain")

    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "yes")
    safety.check_app_allowed("FAKE_VALUE_FOR_TEST-keychain")


def test_high_risk_helper_setting_respects_safe_mode_and_override(monkeypatch):
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    monkeypatch.delenv("DH_SAFE", raising=False)

    with pytest.raises(PermissionError):
        safety.check_helper_allowed("run_shell")

    monkeypatch.setenv("DH_SAFE", "0")
    safety.check_helper_allowed("run_shell")

    monkeypatch.setenv("DH_SAFE", "1")
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    safety.check_helper_allowed("run_shell")


def test_audit_writes_only_to_the_configured_temporary_path(monkeypatch, tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(safety, "_AUDIT", audit_path)

    safety.audit("unit-test", {"case": "temporary-path"})

    rows = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["event"] == "unit-test"
    assert rows[0]["detail"] == {"case": "temporary-path"}
    assert isinstance(rows[0]["ts"], (int, float))


def test_audit_write_errors_are_suppressed(monkeypatch, tmp_path):
    not_a_directory = tmp_path / "not-a-directory"
    not_a_directory.write_text("fixture")
    monkeypatch.setattr(safety, "_AUDIT", not_a_directory / "audit.jsonl")

    # Audit logging is best-effort and must not make the caller fail.
    safety.audit("unit-test", {"case": "unwritable-path"})


def test_audit_log_path_is_loaded_from_environment(monkeypatch, tmp_path):
    configured_path = tmp_path / "configured-audit.jsonl"
    previous_path = safety._AUDIT
    monkeypatch.setenv("DH_AUDIT_LOG", str(configured_path))

    try:
        importlib.reload(safety)
        assert safety._AUDIT == configured_path
    finally:
        # Avoid leaving the reloaded module pointed at any user-configured path.
        safety._AUDIT = previous_path
