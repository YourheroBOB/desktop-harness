"""Pure-logic tests for desktop_harness.windows with mocked AppKit / Quartz.

Covers find_app resolution order (exact > prefix > substring > bundle/pid),
list_apps filtering & sorting, list_windows filtering, frontmost_app.
No real GUI calls: NSWorkspace / NSRunningApplication / Quartz are monkeypatched.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

pytest.importorskip("Quartz")
pytest.importorskip("AppKit")

from desktop_harness import windows  # noqa: E402


# ---------------------------------------------------------------- fakes


class FakeApp:
    def __init__(self, pid, name, bundle="com.example.app",
                 active=False, hidden=False, policy=0):
        self._pid, self._name, self._bundle = pid, name, bundle
        self._active, self._hidden, self._policy = active, hidden, policy

    def activationPolicy(self):
        return self._policy

    def localizedName(self):
        return self._name

    def bundleIdentifier(self):
        return self._bundle

    def processIdentifier(self):
        return self._pid

    def isActive(self):
        return self._active

    def isHidden(self):
        return self._hidden


class FakeWorkspace:
    apps: list = []
    front = None

    @classmethod
    def sharedWorkspace(cls):
        return cls

    @classmethod
    def runningApplications(cls):
        return list(cls.apps)

    @classmethod
    def frontmostApplication(cls):
        return cls.front


class FakeNSRunningApplication:
    by_pid: dict = {}
    by_bundle: list = []

    @staticmethod
    def runningApplicationWithProcessIdentifier_(pid):
        return FakeNSRunningApplication.by_pid.get(pid)

    @staticmethod
    def runningApplicationsWithBundleIdentifier_(bid):
        return list(FakeNSRunningApplication.by_bundle)


APPS = [
    {"name": "TextEdit", "bundle_id": "com.apple.TextEdit", "pid": 100,
     "active": False, "hidden": False},
    {"name": "TextEdit Pro", "bundle_id": "com.example.tep", "pid": 101,
     "active": False, "hidden": False},
    {"name": "Sublime Text", "bundle_id": "com.sublimetext.3", "pid": 102,
     "active": False, "hidden": False},
    {"name": "Terminal", "bundle_id": "com.apple.Terminal", "pid": 103,
     "active": True, "hidden": False},
]


@pytest.fixture
def find_env(monkeypatch):
    monkeypatch.setattr(windows, "list_apps", lambda: [dict(a) for a in APPS])
    FakeNSRunningApplication.by_pid = {}
    FakeNSRunningApplication.by_bundle = []
    monkeypatch.setattr(windows, "NSRunningApplication", FakeNSRunningApplication)


# ---------------------------------------------------------------- list_apps


def test_list_apps_filters_policy_and_sorts(monkeypatch):
    FakeWorkspace.apps = [
        FakeApp(1, "zeta"),
        FakeApp(2, "Alpha", active=True),
        FakeApp(3, "ghost", policy=4),   # accessory/prohibited → dropped
        FakeApp(4, "Beta", active=True),
    ]
    monkeypatch.setattr(windows, "NSWorkspace", FakeWorkspace)
    apps = windows.list_apps()
    names = [a["name"] for a in apps]
    # active first, then name (case-insensitive); non-regular policy dropped
    assert names == ["Alpha", "Beta", "zeta"]
    assert apps[0]["pid"] == 2
    assert apps[0]["bundle_id"] == "com.example.app"
    assert apps[0]["active"] is True
    assert apps[2]["active"] is False
    assert apps[2]["hidden"] is False


# ---------------------------------------------------------------- frontmost_app


def test_frontmost_app_fields(monkeypatch):
    FakeWorkspace.front = FakeApp(9, "Safari", "com.apple.Safari", active=True)
    monkeypatch.setattr(windows, "NSWorkspace", FakeWorkspace)
    f = windows.frontmost_app()
    assert f is not None
    assert f["name"] == "Safari"
    assert f["bundle_id"] == "com.apple.Safari"
    assert f["pid"] == 9
    assert f["active"] is True


def test_frontmost_app_none(monkeypatch):
    FakeWorkspace.front = None
    monkeypatch.setattr(windows, "NSWorkspace", FakeWorkspace)
    assert windows.frontmost_app() is None


# ---------------------------------------------------------------- find_app: strings


def test_find_app_exact_name_case_insensitive(find_env):
    got = windows.find_app("textedit")
    assert got is not None and got["pid"] == 100


def test_find_app_exact_bundle_id(find_env):
    got = windows.find_app("com.apple.textedit")
    assert got is not None and got["pid"] == 100


def test_find_app_exact_beats_substring(find_env):
    # "Terminal" exists exactly; query must not drift to another app
    got = windows.find_app("Terminal")
    assert got is not None and got["pid"] == 103


def test_find_app_prefix_ambiguity_prefers_shortest_name(find_env):
    # "text" is a prefix of both TextEdit and TextEdit Pro → shortest wins
    got = windows.find_app("text")
    assert got is not None and got["pid"] == 100


def test_find_app_prefix_strict(find_env):
    got = windows.find_app("texte")
    assert got is not None and got["pid"] == 100


def test_find_app_substring_prefers_shortest_name(find_env):
    # "edit" only matches as substring; TextEdit is shortest containing name
    got = windows.find_app("edit")
    assert got is not None and got["pid"] == 100


def test_find_app_substring_unique(find_env):
    got = windows.find_app("pro")
    assert got is not None and got["pid"] == 101


def test_find_app_substring_in_bundle_id(find_env):
    got = windows.find_app("sublimetext")
    assert got is not None and got["pid"] == 102


def test_find_app_no_match_returns_none(find_env):
    assert windows.find_app("zzz-no-such-app") is None


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_find_app_empty_query_returns_none(find_env, bad):
    assert windows.find_app(bad) is None


# ---------------------------------------------------------------- find_app: pid & bundle fallback


def test_find_app_by_pid(find_env):
    FakeNSRunningApplication.by_pid = {777: FakeApp(777, "Music", "com.apple.Music")}
    got = windows.find_app(777)
    assert got is not None
    assert got["name"] == "Music"
    assert got["bundle_id"] == "com.apple.Music"
    assert got["pid"] == 777


def test_find_app_unknown_pid_returns_none(find_env):
    FakeNSRunningApplication.by_pid = {}
    assert windows.find_app(424242) is None


def test_find_app_bundle_launch_fallback(find_env):
    # not in list_apps, but NSRunningApplication can resolve the bundle id
    FakeNSRunningApplication.by_bundle = [FakeApp(500, "Fresh", "com.example.fresh")]
    got = windows.find_app("com.example.fresh")
    assert got is not None
    assert got["pid"] == 500
    assert got["name"] == "Fresh"


# ---------------------------------------------------------------- list_windows


def test_list_windows_filters_layers_and_small_windows(monkeypatch):
    raw = [
        {  # kept: layer 0, big enough
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 10, "Y": 20, "Width": 800, "Height": 600},
            "kCGWindowNumber": 11,
            "kCGWindowOwnerName": "Safari",
            "kCGWindowOwnerPID": 5,
            "kCGWindowName": "Welcome",
        },
        {  # dropped: non-zero layer (menu / overlay)
            "kCGWindowLayer": 1,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 1200, "Height": 30},
            "kCGWindowNumber": 12,
            "kCGWindowOwnerName": "MenuBar",
            "kCGWindowOwnerPID": 6,
        },
        {  # dropped: too small (< 50x50)
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 40, "Height": 40},
            "kCGWindowNumber": 13,
            "kCGWindowOwnerName": "Tiny",
            "kCGWindowOwnerPID": 7,
        },
        {  # dropped: zero-size (missing bounds dict)
            "kCGWindowLayer": 0,
            "kCGWindowNumber": 14,
            "kCGWindowOwnerName": "NoBounds",
        },
        {  # kept: defaults for missing owner/title keys
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": "1", "Y": "2", "Width": 100, "Height": 100},
        },
    ]
    seen = {}

    def fake_copy(opts, wid):
        seen["opts"] = opts
        return raw

    fake_quartz = types.SimpleNamespace(
        kCGWindowListOptionOnScreenOnly="ONSCREEN",
        kCGNullWindowID="NULL",
        CGWindowListCopyWindowInfo=fake_copy,
    )
    monkeypatch.setattr(windows, "Quartz", fake_quartz)

    wins = windows.list_windows()
    assert len(wins) == 2

    w = wins[0]
    assert w["id"] == 11
    assert w["app"] == "Safari"
    assert w["pid"] == 5
    assert w["title"] == "Welcome"
    assert w["x"] == 10.0 and w["y"] == 20.0
    assert w["w"] == 800.0 and w["h"] == 600.0

    # defaults when keys are missing
    w2 = wins[1]
    assert w2["app"] == "" and w2["title"] == "" and w2["pid"] == 0 and w2["id"] == 0
    assert w2["x"] == 1.0 and w2["y"] == 2.0  # numeric-string bounds coerced

    # on_screen_only=True passes the on-screen option through
    assert seen["opts"] == "ONSCREEN"


def test_list_windows_all_option_passes_zero(monkeypatch):
    seen = {}

    def fake_copy(opts, wid):
        seen["opts"] = opts
        return []

    fake_quartz = types.SimpleNamespace(
        kCGWindowListOptionOnScreenOnly="ONSCREEN",
        kCGNullWindowID="NULL",
        CGWindowListCopyWindowInfo=fake_copy,
    )
    monkeypatch.setattr(windows, "Quartz", fake_quartz)
    assert windows.list_windows(on_screen_only=False) == []
    assert seen["opts"] == 0
