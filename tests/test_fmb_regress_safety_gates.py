"""回歸測試：safety.py 的敏感 app runtime 閘門。

對應的修復痕跡（見 docs/fmb-adr/ADR-0008、docs/PRE-RELEASE-REVIEW.md #1）：
  * 敏感 app 名稱／bundle 子字串清單已擴充（LastPass / KeePass / Dashlane /
    NordPass / Enpass / secrets / wallet / bank），open + focus 一律拒絕；
  * 第二道閘門：敏感 app **已經在前景**時，變異動作（點擊／輸入／hotkey／
    set_field）也必須被拒 —— 早期版本只擋 open_app／activate；
  * 前景查詢失敗（pyobjc 不可用、windows 匯入失敗等）時必須安靜放行，
    而不是讓整個呼叫炸掉；
  * DH_ALLOW_SENSITIVE=1 是唯一、明確的逃生口；
  * check_helper_allowed 是 safe-mode 下的高風險 helper hook。

本檔只依賴純 Python 的 safety.py，不需要 pyobjc、不開視窗、不連網路。
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import desktop_harness  # noqa: E402
from desktop_harness import safety  # noqa: E402


# 名稱子字串清單（ADR-0008：substring 為現況，過寬是已知取捨）
SENSITIVE_NAMES = [
    "1Password",
    "Bitwarden",
    "Keychain Access",
    "LastPass",
    "KeePassXC",
    "Dashlane",
    "NordPass",
    "Enpass",
    "Secrets",
    "Apple Wallet",
    "Bank of Example",
]

SENSITIVE_BUNDLES = [
    "com.1password.1password",
    "com.bitwarden.desktop",
    "com.apple.keychainaccess",
    "com.lastpass.LastPass",
    "org.keepassxc.keepassxc",
    "com.dashlane.dashlane",
    "com.nordpass.NordPass",
    "com.enpass.Enpass",
]

ORDINARY_APPS = [
    "TextEdit",
    "Safari",
    "Finder",
    "Terminal",
    "Google Chrome",
    "Xcode",
    "Notes",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """每個測試都從「預設政策」開始：不覆寫、安全模式開啟。"""
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    monkeypatch.delenv("DH_SAFE", raising=False)


def _fake_windows(monkeypatch, frontmost):
    """把 .windows 換成假的：frontmost 可為 dict / None / 例外。"""
    mod = types.ModuleType("desktop_harness.windows")

    def frontmost_app():
        if isinstance(frontmost, BaseException):
            raise frontmost
        return frontmost

    mod.frontmost_app = frontmost_app
    monkeypatch.setitem(sys.modules, "desktop_harness.windows", mod)
    monkeypatch.setattr(desktop_harness, "windows", mod, raising=False)
    return mod


# --------------------------------------------------------------------------
# 名稱 / bundle gate
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", SENSITIVE_NAMES)
def test_sensitive_app_names_are_blocked(name):
    with pytest.raises(PermissionError) as exc:
        safety.check_app_allowed(name)
    assert "DH_ALLOW_SENSITIVE" in str(exc.value)


@pytest.mark.parametrize("bundle", SENSITIVE_BUNDLES)
def test_sensitive_bundle_ids_are_blocked(bundle):
    with pytest.raises(PermissionError):
        safety.check_app_allowed("Some Helper", bundle)


def test_name_alone_is_enough_to_block():
    with pytest.raises(PermissionError):
        safety.check_app_allowed("1Password", "")


@pytest.mark.parametrize("name", ORDINARY_APPS)
def test_ordinary_apps_are_allowed(name):
    assert safety.check_app_allowed(name) is None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_allow_sensitive_escape_hatch(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    assert safety.allow_sensitive() is True
    assert safety.check_app_allowed("1Password", "com.1password.1password") is None


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_allow_sensitive_non_truthy_values(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    assert safety.allow_sensitive() is False
    with pytest.raises(PermissionError):
        safety.check_app_allowed("Bitwarden")


# --------------------------------------------------------------------------
# 前景 gate（review #1 的核心缺口）
# --------------------------------------------------------------------------
def test_frontmost_sensitive_app_blocks_mutation(monkeypatch):
    _fake_windows(
        monkeypatch,
        {"name": "1Password", "bundle_id": "com.1password.1password"},
    )
    with pytest.raises(PermissionError):
        safety.check_frontmost_allowed()


def test_frontmost_sensitive_bundle_blocks_mutation(monkeypatch):
    _fake_windows(
        monkeypatch,
        {"name": "Some App", "bundle_id": "com.bitwarden.desktop"},
    )
    with pytest.raises(PermissionError):
        safety.check_frontmost_allowed()


def test_frontmost_ordinary_app_is_fine(monkeypatch):
    _fake_windows(
        monkeypatch,
        {"name": "TextEdit", "bundle_id": "com.apple.TextEdit"},
    )
    assert safety.check_frontmost_allowed() is None


def test_frontmost_unknown_app_is_fine(monkeypatch):
    _fake_windows(monkeypatch, None)
    assert safety.check_frontmost_allowed() is None


def test_frontmost_lookup_failure_does_not_break_the_call(monkeypatch):
    """防禦性檢查：查不到前景 app 時不可把整個動作炸掉。"""
    _fake_windows(monkeypatch, RuntimeError("pyobjc unavailable"))
    assert safety.check_frontmost_allowed() is None


def test_frontmost_gate_respects_escape_hatch(monkeypatch):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    _fake_windows(
        monkeypatch,
        {"name": "KeePassXC", "bundle_id": "org.keepassxc.keepassxc"},
    )
    assert safety.check_frontmost_allowed() is None


# --------------------------------------------------------------------------
# safe mode / 高風險 helper hook
# --------------------------------------------------------------------------
def test_safe_mode_defaults_on():
    assert safety.safe_mode() is True


@pytest.mark.parametrize("value", ["0", "false", "no"])
def test_safe_mode_can_be_disabled(monkeypatch, value):
    monkeypatch.setenv("DH_SAFE", value)
    assert safety.safe_mode() is False


@pytest.mark.parametrize("helper", ["run_shell", "shell", "osascript_raw"])
def test_high_risk_helper_names_blocked_in_safe_mode(helper):
    with pytest.raises(PermissionError):
        safety.check_helper_allowed(helper)


def test_high_risk_helper_allowed_when_safe_mode_off(monkeypatch):
    monkeypatch.setenv("DH_SAFE", "0")
    assert safety.check_helper_allowed("run_shell") is None


def test_regular_helpers_are_not_blocked():
    for helper in ("click_text", "type_text", "screenshot", "labels"):
        assert safety.check_helper_allowed(helper) is None
