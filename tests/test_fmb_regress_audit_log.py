"""回歸測試：audit log 的寫入格式與容錯。

對應的修復痕跡（見 docs/fmb-adr/ADR-0008、docs/fmb-perf/findings-timeouts-recovery.md
TR-4 的後續硬化）：
  * audit() 會自動建立父目錄（~/.desktop-harness 不存在時不可失敗）；
  * 每次呼叫 append 一行合法 JSON（NDJSON），欄位為 ts / event / detail；
  * detail 內含不可序列化物件時以 default=str 收斂，不可整筆丟掉；
  * 寫入失敗一律安靜吞掉 —— 審計不可反過來中斷控制流程；
  * DH_AUDIT_LOG 可覆寫路徑（測試／多 profile 隔離用）。

所有寫入都落在 pytest 的 tmp_path，不碰使用者真實的 audit log。
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_harness import safety  # noqa: E402


@pytest.fixture()
def audit_path(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "audit.jsonl"
    monkeypatch.setattr(safety, "_AUDIT", path)
    return path


def _rows(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_audit_creates_parent_dir_and_appends(audit_path):
    assert not audit_path.parent.exists()
    safety.audit("click_text", {"target": "Save", "app": "TextEdit"})
    safety.audit("activate", {"app": "TextEdit"})

    rows = _rows(audit_path)
    assert [r["event"] for r in rows] == ["click_text", "activate"]
    assert set(rows[0]) == {"ts", "event", "detail"}
    assert isinstance(rows[0]["ts"], float)
    assert rows[0]["detail"] == {"target": "Save", "app": "TextEdit"}


def test_audit_detail_defaults_to_empty_dict(audit_path):
    safety.audit("screenshot")
    assert _rows(audit_path)[0]["detail"] == {}


def test_audit_serialises_unexpected_detail_values(audit_path):
    class _Opaque:
        def __str__(self):
            return "opaque-for-test"

    safety.audit("click_text", {"target": _Opaque(), "n": 3})
    detail = _rows(audit_path)[0]["detail"]
    assert detail["target"] == "opaque-for-test"
    assert detail["n"] == 3


def test_audit_failure_is_swallowed(tmp_path, monkeypatch):
    """父路徑被一般檔案佔住時，audit 必須安靜失敗、不可丟例外。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(safety, "_AUDIT", blocker / "audit.jsonl")

    assert safety.audit("click_text", {"target": "Save"}) is None
    assert blocker.read_text(encoding="utf-8") == "not a directory"


def test_each_call_produces_exactly_one_line(audit_path):
    for i in range(5):
        safety.audit("click_text", {"target": f"item-{i}"})
    text = audit_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert len([ln for ln in text.splitlines() if ln.strip()]) == 5


def test_audit_log_path_env_override(monkeypatch, tmp_path):
    """DH_AUDIT_LOG 在 import 時生效（避免寫到使用者真實 log）。"""
    target = tmp_path / "env-audit.jsonl"
    monkeypatch.setenv("DH_AUDIT_LOG", str(target))
    try:
        importlib.reload(safety)
        assert Path(safety._AUDIT) == target
        safety.audit("daemon_start", {"pid": 4242})
        rows = _rows(target)
        assert rows[0]["event"] == "daemon_start"
        assert rows[0]["detail"] == {"pid": 4242}
    finally:
        monkeypatch.delenv("DH_AUDIT_LOG", raising=False)
        importlib.reload(safety)
