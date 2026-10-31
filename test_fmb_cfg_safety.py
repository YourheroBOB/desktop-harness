"""設定與環境變數測試；所有檔案操作都限制在 pytest 暫存目錄。"""
from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


# 從本地 src layout 載入待測套件，不依賴全域安裝。
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


@pytest.fixture
def safety_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("DH_AUDIT_LOG", str(audit_path))

    module = importlib.import_module("desktop_harness.safety")
    # 即使其他測試已載入模組，也只讓本測試寫入 tmp_path。
    monkeypatch.setattr(module, "_AUDIT", audit_path)
    return module


@pytest.mark.parametrize("value", ["1", "TRUE", "Yes"])
def test_allow_sensitive_accepts_documented_truthy_values(
    safety_module, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)

    assert safety_module.allow_sensitive() is True


@pytest.mark.parametrize("value", ["", "0", "false", "unexpected"])
def test_allow_sensitive_defaults_to_false_for_unset_or_unrecognized_values(
    safety_module, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    if value:
        monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    else:
        monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)

    assert safety_module.allow_sensitive() is False


def test_safe_mode_defaults_to_enabled(
    safety_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DH_SAFE", raising=False)

    assert safety_module.safe_mode() is True


@pytest.mark.parametrize("value", ["0", "FALSE", "no"])
def test_safe_mode_can_be_disabled_by_documented_values(
    safety_module, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DH_SAFE", value)

    assert safety_module.safe_mode() is False


def test_safe_mode_treats_unrecognized_value_as_enabled(
    safety_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DH_SAFE", "unexpected")

    assert safety_module.safe_mode() is True


def test_sensitive_app_name_and_bundle_are_blocked_by_default(
    safety_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)

    with pytest.raises(PermissionError):
        safety_module.check_app_allowed("FAKE_KEYCHAIN_FOR_TEST")

    with pytest.raises(PermissionError):
        safety_module.check_app_allowed(
            "FAKE_APP_FOR_TEST",
            bundle_id="org.example.bitwarden.fake",
        )


def test_allow_sensitive_override_allows_sensitive_app(
    safety_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")

    safety_module.check_app_allowed("FAKE_KEYCHAIN_FOR_TEST")


def test_frontmost_sensitive_app_is_checked_without_native_app_imports(
    safety_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    import desktop_harness

    fake_windows = types.ModuleType("desktop_harness.windows")
    fake_windows.frontmost_app = lambda: {
        "name": "FAKE_KEYCHAIN_FOR_TEST",
        "bundle_id": "",
    }
    monkeypatch.setitem(sys.modules, "desktop_harness.windows", fake_windows)
    monkeypatch.setattr(desktop_harness, "windows", fake_windows, raising=False)
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)

    with pytest.raises(PermissionError):
        safety_module.check_frontmost_allowed()


def test_frontmost_check_fails_open_if_detection_raises(
    safety_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    import desktop_harness

    fake_windows = types.ModuleType("desktop_harness.windows")

    def unavailable_frontmost_app():
        raise RuntimeError("fake detection failure")

    fake_windows.frontmost_app = unavailable_frontmost_app
    monkeypatch.setitem(sys.modules, "desktop_harness.windows", fake_windows)
    monkeypatch.setattr(desktop_harness, "windows", fake_windows, raising=False)

    safety_module.check_frontmost_allowed()


def test_audit_log_path_is_loaded_from_environment(
    safety_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_audit_path = safety_module._AUDIT
    configured_path = tmp_path / "configured-audit.jsonl"
    monkeypatch.setenv("DH_AUDIT_LOG", str(configured_path))

    try:
        importlib.reload(safety_module)
        assert safety_module._AUDIT == configured_path
    finally:
        safety_module._AUDIT = original_audit_path


def test_audit_writes_jsonl_only_under_tmp_path(
    safety_module, tmp_path: Path
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    safety_module._AUDIT = audit_path

    safety_module.audit("test_event", {"source": "unit-test"})

    rows = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["event"] == "test_event"
    assert rows[0]["detail"] == {"source": "unit-test"}


def test_audit_swallows_invalid_destination_errors(
    safety_module, tmp_path: Path
) -> None:
    # 將既有目錄當成檔案路徑，模擬無法開啟 audit log 的情況。
    safety_module._AUDIT = tmp_path

    safety_module.audit("test_event")
