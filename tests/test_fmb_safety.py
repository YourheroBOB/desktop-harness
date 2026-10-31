"""Unit tests for desktop_harness.safety — sensitive-app gates, safe mode, audit log.

Pure-stdlib module: no macOS frameworks, no real GUI interaction, no network.
All file writes go to pytest tmp_path via monkeypatched module attributes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from desktop_harness import safety  # noqa: E402

try:
    from desktop_harness import windows as _windows  # noqa: E402
except Exception:  # pyobjc unavailable in this environment
    _windows = None


@pytest.fixture(autouse=True)
def _neutral_env(monkeypatch):
    """Make gate results independent of the ambient shell environment."""
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    monkeypatch.delenv("DH_SAFE", raising=False)


# ---------------------------------------------------------------- _looks_sensitive

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
    "Wallet",
    "My Bank App",
]

BENIGN_NAMES = ["TextEdit", "Safari", "Finder", "Music", "Terminal", "Notes"]


@pytest.mark.parametrize("name", SENSITIVE_NAMES)
def test_looks_sensitive_matches_sensitive_names(name):
    assert safety._looks_sensitive(name) is True


@pytest.mark.parametrize("name", BENIGN_NAMES)
def test_looks_sensitive_allows_benign_names(name):
    assert safety._looks_sensitive(name) is False


@pytest.mark.parametrize("name", ["BITWARDEN", "LASTPASS", "1PASSWORD", "KeyChain"])
def test_looks_sensitive_is_case_insensitive(name):
    assert safety._looks_sensitive(name) is True


@pytest.mark.parametrize(
    "bundle",
    [
        "com.agilebits.1password",
        "com.bitwarden.desktop",
        "com.apple.keychainaccess",
        "com.lastpass.LastPass",
    ],
)
def test_looks_sensitive_matches_sensitive_bundles(bundle):
    assert safety._looks_sensitive("", bundle) is True


def test_looks_sensitive_benign_bundle():
    assert safety._looks_sensitive("", "com.apple.Safari") is False


def test_looks_sensitive_empty_inputs():
    assert safety._looks_sensitive("", "") is False
    assert safety._looks_sensitive() is False


# ---------------------------------------------------------------- allow / safe mode


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
def test_allow_sensitive_truthy_values(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    assert safety.allow_sensitive() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_allow_sensitive_falsy_values(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    assert safety.allow_sensitive() is False


def test_allow_sensitive_unset(monkeypatch):
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    assert safety.allow_sensitive() is False


def test_safe_mode_default_on(monkeypatch):
    monkeypatch.delenv("DH_SAFE", raising=False)
    assert safety.safe_mode() is True


@pytest.mark.parametrize("value", ["0", "false", "no"])
def test_safe_mode_can_be_disabled(monkeypatch, value):
    monkeypatch.setenv("DH_SAFE", value)
    assert safety.safe_mode() is False


@pytest.mark.parametrize("value", ["1", "true", "anything-else"])
def test_safe_mode_stays_on_for_other_values(monkeypatch, value):
    monkeypatch.setenv("DH_SAFE", value)
    assert safety.safe_mode() is True


# ---------------------------------------------------------------- check_app_allowed


def test_check_app_allowed_blocks_sensitive_name():
    with pytest.raises(PermissionError) as ei:
        safety.check_app_allowed("1Password", "com.agilebits.1password")
    assert "1Password" in str(ei.value)
    assert "DH_ALLOW_SENSITIVE" in str(ei.value)


def test_check_app_allowed_blocks_by_bundle_only():
    with pytest.raises(PermissionError):
        safety.check_app_allowed("Some Innocent Name", "com.example.bitwarden.helper")


def test_check_app_allowed_allows_benign():
    assert safety.check_app_allowed("TextEdit", "com.apple.TextEdit") is None
    assert safety.check_app_allowed("Safari") is None


@pytest.mark.parametrize("value", ["1", "true", "yes"])
def test_check_app_allowed_override_env(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    assert safety.check_app_allowed("1Password") is None


# ---------------------------------------------------------------- check_helper_allowed


@pytest.mark.parametrize("name", ["run_shell", "shell", "osascript_raw"])
def test_check_helper_allowed_blocks_high_risk_names(name):
    with pytest.raises(PermissionError, match="safe mode"):
        safety.check_helper_allowed(name)


def test_check_helper_allowed_normal_helpers_pass():
    assert safety.check_helper_allowed("list_apps") is None
    assert safety.check_helper_allowed("click_text") is None


def test_check_helper_allowed_disabled_when_safe_mode_off(monkeypatch):
    monkeypatch.setenv("DH_SAFE", "0")
    assert safety.check_helper_allowed("run_shell") is None


def test_check_helper_allowed_disabled_when_sensitive_allowed(monkeypatch):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    assert safety.check_helper_allowed("run_shell") is None


# ---------------------------------------------------------------- audit log


def test_audit_writes_valid_jsonl(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr(safety, "_AUDIT", log)
    safety.audit("click_text", {"app": "TextEdit", "text": "Save"})
    safety.audit("activate")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["event"] == "click_text"
    assert row["detail"] == {"app": "TextEdit", "text": "Save"}
    assert isinstance(row["ts"], float)
    row2 = json.loads(lines[1])
    assert row2["event"] == "activate"
    assert row2["detail"] == {}


def test_audit_never_raises_on_unwritable_path(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(safety, "_AUDIT", blocker / "audit.jsonl")
    # must be swallowed silently, not raise
    safety.audit("some_event", {"k": "FAKE_VALUE_FOR_TEST"})


# ---------------------------------------------------------------- check_frontmost_allowed


@pytest.mark.skipif(_windows is None, reason="desktop_harness.windows needs pyobjc")
class TestCheckFrontmostAllowed:
    def test_blocks_sensitive_frontmost(self, monkeypatch):
        monkeypatch.setattr(_windows, "frontmost_app", lambda: {
            "name": "1Password", "bundle_id": "com.agilebits.1password",
            "pid": 4321, "active": True, "hidden": False,
        })
        with pytest.raises(PermissionError):
            safety.check_frontmost_allowed()

    def test_allows_benign_frontmost(self, monkeypatch):
        monkeypatch.setattr(_windows, "frontmost_app", lambda: {
            "name": "TextEdit", "bundle_id": "com.apple.TextEdit",
            "pid": 1234, "active": True, "hidden": False,
        })
        assert safety.check_frontmost_allowed() is None

    def test_none_frontmost_is_ok(self, monkeypatch):
        monkeypatch.setattr(_windows, "frontmost_app", lambda: None)
        assert safety.check_frontmost_allowed() is None

    def test_swallows_perception_errors(self, monkeypatch):
        def boom():
            raise RuntimeError("no AX permission")
        monkeypatch.setattr(_windows, "frontmost_app", boom)
        assert safety.check_frontmost_allowed() is None

    def test_override_env_unblocks_sensitive_frontmost(self, monkeypatch):
        monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
        monkeypatch.setattr(_windows, "frontmost_app", lambda: {
            "name": "Bitwarden", "bundle_id": "com.bitwarden.desktop",
            "pid": 99, "active": True, "hidden": False,
        })
        assert safety.check_frontmost_allowed() is None


# ---------------------------------------------------------------- guidance


def test_confirm_guidance_mentions_stopping():
    assert isinstance(safety.CONFIRM_GUIDANCE, str)
    assert "ask the user" in safety.CONFIRM_GUIDANCE
