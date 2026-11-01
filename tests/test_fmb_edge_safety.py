"""Edge-case and error-path tests for ``desktop_harness.safety`` (fmb edge suite).

Focus: boundary inputs and failure handling that happy-path suites do not cover —
env-var parsing extremes, substring-match boundaries, gate ordering, audit-log
integrity, and audit-log failure containment.

Nothing here touches a real desktop or the network: every audit write is
redirected into ``tmp_path``, every frontmost lookup is injected, and the two
subprocess checks run with ``HOME`` pointed at a temporary directory.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_harness import safety  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_audit(tmp_path, monkeypatch):
    """Keep ``safety.audit()`` inside tmp_path and reset DH_* to defaults."""
    log_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(safety, "_AUDIT", log_path)
    for name in ("DH_ALLOW_SENSITIVE", "DH_SAFE", "DH_AUDIT_LOG"):
        monkeypatch.delenv(name, raising=False)
    return log_path


@pytest.fixture
def install_fake_windows(monkeypatch):
    """Swap ``desktop_harness.windows`` for a stub with an injectable ``frontmost_app``."""
    import desktop_harness

    def _install(frontmost_app):
        module = types.ModuleType("desktop_harness.windows")
        module.frontmost_app = frontmost_app
        monkeypatch.setitem(sys.modules, "desktop_harness.windows", module)
        monkeypatch.setattr(desktop_harness, "windows", module, raising=False)
        return module

    return _install


def _run_python(code: str, *, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("DH_")}
    clean_env.update(
        {
            "PYTHONPATH": str(SRC),
            "HOME": str(cwd),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    clean_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", code],
        env=clean_env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# env-var parsing boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value", ["1", "true", "True", "TRUE", "tRuE", "yes", "YES", "Yes"]
)
def test_allow_sensitive_true_variants(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    assert safety.allow_sensitive() is True


@pytest.mark.parametrize(
    "value",
    ["", "0", "2", "no", "nope", "y", "on", " true", "true ", "false", "01"],
)
def test_allow_sensitive_false_variants(monkeypatch, value):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", value)
    assert safety.allow_sensitive() is False


def test_safe_mode_defaults_on_when_env_missing():
    assert safety.safe_mode() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "False", "no", "NO"])
def test_safe_mode_off_variants(monkeypatch, value):
    monkeypatch.setenv("DH_SAFE", value)
    assert safety.safe_mode() is False


@pytest.mark.parametrize("value", ["", "1", "true", "yes", "maybe", "00", "n"])
def test_safe_mode_on_variants(monkeypatch, value):
    monkeypatch.setenv("DH_SAFE", value)
    assert safety.safe_mode() is True


# ---------------------------------------------------------------------------
# sensitive-name matching boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("name", "bundle_id", "expected"),
    [
        ("", "", False),
        ("Finder", "com.apple.finder", False),
        ("Notes", "", False),
        ("1Password", "", True),
        ("1password", "", True),
        ("GoodNotes", "", False),
        # bundle-only marker in the *name* slot is not a name-substring hit
        ("com.agilebits.onepassword7", "", False),
        # ...but the same marker in the bundle slot is
        ("Some App", "com.1password.1password", True),
        ("", "com.bitwarden.desktop", True),
        ("Keychain Access", "com.apple.keychainaccess", True),
        ("Apple Wallet", "", True),
        # documented over-block: substring "bank" is broad on purpose
        ("Sound Bank Mixer", "", True),
        ("bankrupt-app", "", True),
        # "wallet" is name-only in the current lists; bundle-only wallet passes
        ("Some App", "com.example.wallet", False),
    ],
)
def test_looks_sensitive_boundaries(name, bundle_id, expected):
    assert safety._looks_sensitive(name, bundle_id) is expected


def test_looks_sensitive_without_arguments_is_false():
    assert safety._looks_sensitive() is False


def test_sensitive_lists_are_lowercase_and_nonempty():
    names = safety._SENSITIVE_NAME_SUBSTR
    bundles = safety._SENSITIVE_BUNDLE_SUBSTR
    assert len(names) > 0
    assert len(bundles) > 0
    for token in names + bundles:
        assert isinstance(token, str)
        assert token != ""
        assert token == token.lower()


# ---------------------------------------------------------------------------
# check_app_allowed
# ---------------------------------------------------------------------------

def test_check_app_allowed_blocks_and_hints_the_override():
    with pytest.raises(PermissionError) as excinfo:
        safety.check_app_allowed("1Password", "com.1password.1password")
    message = str(excinfo.value)
    assert "DH_ALLOW_SENSITIVE" in message
    assert "1Password" in message


def test_check_app_allowed_message_survives_missing_bundle():
    with pytest.raises(PermissionError) as excinfo:
        safety.check_app_allowed("Keychain Access")
    assert "no bundle" in str(excinfo.value)


def test_check_app_allowed_allows_neutral_app():
    assert safety.check_app_allowed("Safari", "com.apple.Safari") is None


def test_check_app_allowed_allows_empty_name():
    assert safety.check_app_allowed("") is None


def test_check_app_allowed_blocks_bundle_only_match():
    with pytest.raises(PermissionError):
        safety.check_app_allowed("Notes", "com.lastpass.notes")


def test_check_app_allowed_override_env(monkeypatch):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    assert safety.check_app_allowed("1Password") is None


# ---------------------------------------------------------------------------
# check_frontmost_allowed
# ---------------------------------------------------------------------------

def test_frontmost_gate_allows_no_frontmost_app(install_fake_windows):
    install_fake_windows(lambda: None)
    assert safety.check_frontmost_allowed() is None


def test_frontmost_gate_allows_neutral_app(install_fake_windows):
    install_fake_windows(lambda: {"name": "Safari", "bundle_id": "com.apple.Safari"})
    assert safety.check_frontmost_allowed() is None


def test_frontmost_gate_blocks_sensitive_name(install_fake_windows):
    install_fake_windows(
        lambda: {"name": "1Password", "bundle_id": "com.1password.1password"}
    )
    with pytest.raises(PermissionError):
        safety.check_frontmost_allowed()


def test_frontmost_gate_blocks_sensitive_bundle_without_name(install_fake_windows):
    install_fake_windows(lambda: {"bundle_id": "com.bitwarden.desktop"})
    with pytest.raises(PermissionError):
        safety.check_frontmost_allowed()


def test_frontmost_gate_handles_none_valued_fields(install_fake_windows):
    install_fake_windows(lambda: {"name": None, "bundle_id": None})
    assert safety.check_frontmost_allowed() is None


def test_frontmost_gate_handles_empty_mapping(install_fake_windows):
    install_fake_windows(dict)
    assert safety.check_frontmost_allowed() is None


def test_frontmost_gate_ignores_lookup_failure(install_fake_windows):
    def boom():
        raise RuntimeError("AX/NSWorkspace unavailable")

    install_fake_windows(boom)
    assert safety.check_frontmost_allowed() is None


def test_frontmost_gate_override_env(install_fake_windows, monkeypatch):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "yes")
    install_fake_windows(lambda: {"name": "Bitwarden"})
    assert safety.check_frontmost_allowed() is None


def test_frontmost_gate_consults_frontmost_exactly_once(install_fake_windows):
    calls = []

    def front():
        calls.append("called")
        return {"name": "Safari"}

    install_fake_windows(front)
    safety.check_frontmost_allowed()
    assert calls == ["called"]


# ---------------------------------------------------------------------------
# check_helper_allowed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("helper", ["run_shell", "shell", "osascript_raw"])
def test_blocked_helper_raises_in_safe_mode(helper):
    with pytest.raises(PermissionError) as excinfo:
        safety.check_helper_allowed(helper)
    assert helper in str(excinfo.value)


@pytest.mark.parametrize("helper", ["", "click_text", "type_text", "RUN_SHELL"])
def test_non_blocked_helper_passes(helper):
    # Names are matched case-sensitively; only the exact frozen set blocks.
    assert safety.check_helper_allowed(helper) is None


def test_blocked_helper_passes_when_safe_mode_off(monkeypatch):
    monkeypatch.setenv("DH_SAFE", "0")
    assert safety.check_helper_allowed("run_shell") is None


def test_blocked_helper_passes_with_sensitive_override(monkeypatch):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    assert safety.check_helper_allowed("run_shell") is None


# ---------------------------------------------------------------------------
# audit()
# ---------------------------------------------------------------------------

def test_audit_writes_one_json_line(isolated_audit):
    safety.audit("click_text", {"label": "Save"})
    lines = isolated_audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event"] == "click_text"
    assert row["detail"] == {"label": "Save"}
    assert isinstance(row["ts"], float)
    assert row["ts"] > 0


def test_audit_default_detail_is_empty_dict(isolated_audit):
    safety.audit("activate")
    row = json.loads(isolated_audit.read_text(encoding="utf-8").splitlines()[-1])
    assert row["detail"] == {}


def test_audit_appends_in_order(isolated_audit):
    safety.audit("first")
    safety.audit("second")
    rows = [
        json.loads(line)
        for line in isolated_audit.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event"] for row in rows] == ["first", "second"]


def test_audit_keeps_newlines_inside_one_jsonl_record(isolated_audit):
    safety.audit("line\nbreak", {"note": "two\nlines"})
    lines = isolated_audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event"] == "line\nbreak"
    assert row["detail"] == {"note": "two\nlines"}


def test_audit_serialises_unknown_objects_defensively(isolated_audit):
    class Opaque:
        def __repr__(self):
            return "<opaque>"

    safety.audit("mutate", {"obj": Opaque(), "blob": b"\x00\x01"})
    row = json.loads(isolated_audit.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(row["detail"]["obj"], str)
    assert isinstance(row["detail"]["blob"], str)


def test_audit_creates_missing_parent_directories(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "deeper" / "audit.jsonl"
    monkeypatch.setattr(safety, "_AUDIT", target)
    safety.audit("event")
    assert target.is_file()


def test_audit_swallows_unwritable_path(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(safety, "_AUDIT", blocker / "audit.jsonl")
    assert safety.audit("event") is None


def test_audit_swallows_serialisation_failure(isolated_audit):
    class Bad:
        def __repr__(self):
            raise RuntimeError("cannot stringify")

        __str__ = __repr__

    assert safety.audit("odd", {"bad": Bad()}) is None
    # The record may be truncated/empty; what matters is the call never raises.
    assert not isolated_audit.exists() or isolated_audit.read_text(
        encoding="utf-8"
    ).strip() == ""


# ---------------------------------------------------------------------------
# import-time side effects / env wiring, verified in a clean subprocess
# ---------------------------------------------------------------------------

def test_import_does_not_create_home_state(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    proc = _run_python(
        "import desktop_harness.safety as s\nprint(s.safe_mode())\n",
        env={},
        cwd=home,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "True"
    assert list(home.iterdir()) == []


def test_audit_log_env_override_is_honoured(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "custom" / "audit.jsonl"
    code = (
        "import desktop_harness.safety as s\n"
        "s.audit('ping', {'k': 1})\n"
        "print(s._AUDIT)\n"
    )
    proc = _run_python(code, env={"DH_AUDIT_LOG": str(log)}, cwd=home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(log)
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["event"] == "ping"
    assert rows[0]["detail"] == {"k": 1}
    assert not (home / ".desktop-harness").exists()


def test_sensitive_override_env_is_honoured_in_subprocess(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    code = (
        "import desktop_harness.safety as s\n"
        "try:\n"
        "    s.check_app_allowed('1Password')\n"
        "except PermissionError:\n"
        "    print('blocked')\n"
        "else:\n"
        "    print('allowed')\n"
    )
    blocked = _run_python(code, env={}, cwd=home)
    allowed = _run_python(code, env={"DH_ALLOW_SENSITIVE": "1"}, cwd=home)
    assert blocked.returncode == 0, blocked.stderr
    assert allowed.returncode == 0, allowed.stderr
    assert blocked.stdout.strip() == "blocked"
    assert allowed.stdout.strip() == "allowed"
