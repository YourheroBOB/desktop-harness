"""Public contract tests for desktop_harness.safety.

These tests use only local environment variables and tmp_path; they do not
interact with the desktop or write outside the test sandbox.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Support running pytest from a source checkout without an editable install.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import desktop_harness
from desktop_harness import safety


def test_public_function_signatures_remain_stable():
    assert list(inspect.signature(safety.allow_sensitive).parameters) == []
    assert list(inspect.signature(safety.safe_mode).parameters) == []

    check_app_params = inspect.signature(safety.check_app_allowed).parameters
    assert list(check_app_params) == ["name", "bundle_id"]
    assert check_app_params["bundle_id"].default == ""

    assert list(inspect.signature(safety.check_frontmost_allowed).parameters) == []
    assert list(inspect.signature(safety.check_helper_allowed).parameters) == ["name"]

    audit_params = inspect.signature(safety.audit).parameters
    assert list(audit_params) == ["event", "detail"]
    assert audit_params["detail"].default is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
    ],
)
def test_allow_sensitive_environment_contract(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    else:
        monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)

    assert safety.allow_sensitive() is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("1", True),
        ("false", False),
        ("no", False),
        ("0", False),
    ],
)
def test_safe_mode_environment_contract(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("DH_SAFE", raising=False)
    else:
        monkeypatch.setenv("DH_SAFE", value)

    assert safety.safe_mode() is expected


def test_check_app_allowed_return_and_error_contract(monkeypatch):
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)

    assert safety.check_app_allowed("Example Editor") is None
    with pytest.raises(PermissionError):
        safety.check_app_allowed("Bitwarden Desktop")

    # Explicit override remains supported for both name and bundle checks.
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    assert safety.check_app_allowed(
        "Example App", bundle_id="com.example.keychain-helper"
    ) is None


def test_check_frontmost_allowed_blocks_sensitive_frontmost_app(monkeypatch):
    monkeypatch.delenv("DH_ALLOW_SENSITIVE", raising=False)
    monkeypatch.setattr(
        desktop_harness,
        "windows",
        SimpleNamespace(
            frontmost_app=lambda: {
                "name": "Example Keychain Helper",
                "bundle_id": "com.example.keychain-helper",
            }
        ),
        raising=False,
    )

    with pytest.raises(PermissionError):
        safety.check_frontmost_allowed()


def test_audit_writes_one_jsonl_record_in_the_test_sandbox(monkeypatch, tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(safety, "_AUDIT", audit_path)

    assert safety.audit(
        "contract-event", {"count": 2, "marker": "FAKE_VALUE_FOR_TEST"}
    ) is None

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert set(record) == {"ts", "event", "detail"}
    assert isinstance(record["ts"], (int, float))
    assert record["event"] == "contract-event"
    assert record["detail"] == {
        "count": 2,
        "marker": "FAKE_VALUE_FOR_TEST",
    }
