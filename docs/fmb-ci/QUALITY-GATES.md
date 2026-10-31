# L1–L2：Lint、型別、測試、覆蓋率

## 工具選擇（保守理由）

| 關卡 | 工具 | 為什麼 |
|------|------|--------|
| Lint | **ruff**（含 `ruff format --check`） | 單一工具涵蓋 flake8/isort/pyupgrade；repo 零現有設定，導入摩擦最低 |
| 型別 | **mypy**（漸進式） | pyobjc 沒有完整 stubs → `ignore_missing_imports = true`，先求「不新增型別錯誤」 |
| 測試 | **pytest**（+ `pytest-cov`） | 業界標準；`tmp_path` fixture 直接對應本 repo 的沙箱驗證原則 |
| 覆蓋率 | 只報告、**初期不設 fail 門檻 | repo 目前測試數為 0；先設門檻只會逼人寫垃圾測試或直接關掉關卡 |

## `pyproject.toml` 設定片段（可直接貼上，追加到現有檔尾）

```toml
[tool.ruff]
line-length = 100
target-version = "py310"
src = ["src", "scripts"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]
# B（bugbear）值得開：本 repo 的教訓多是邏輯/資源類 bug
ignore = [
  "E501",  # line-length 由 formatter 管，硬擋會與現有長字串衝突
]

[tool.ruff.lint.per-file-ignores]
"scripts/voice_session.py" = ["UP"]  # 實驗性腳本，先不動

[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true        # pyobjc / AppKit 無完整 stubs
check_untyped_defs = true
no_implicit_optional = true
warn_unused_ignores = true
files = ["src/desktop_harness"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"
markers = [
  "macos_gui: needs real macOS GUI permissions (excluded from CI by default)",
]
```

## 測試檔案建議結構（第一步 PR 的範圍）

```text
tests/
  conftest.py          # 共用 fixture：沙箱環境變數、mock Quartz/AppKit
  test_safety.py       # check_app_allowed / check_frontmost_allowed / allow_sensitive
                       # —— 純邏輯，mock frontmost_app()，直接驗證 ADR-0008 的宣稱
  test_cli_smoke.py    # --version / --help / skill 輸出非空（subprocess 呼叫）
```

`conftest.py` 的沙箱骨架（所有測試共通，呼應 verification-plan.md 的隔離矩陣）：

```python
import os
import pytest

@pytest.fixture(autouse=True)
def sandbox_env(monkeypatch, tmp_path):
    """每個測試都在 tmp 沙箱內，不碰使用者的 daemon / audit log / repo 外路徑。"""
    monkeypatch.setenv("DH_SOCKET", str(tmp_path / "test.sock"))
    monkeypatch.setenv("DH_TOKEN_PATH", str(tmp_path / "test.token"))
    monkeypatch.setenv("DH_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("DH_NO_DAEMON", "1")
    monkeypatch.setenv("XAI_API_KEY", "FAKE_VALUE_FOR_TEST")
    monkeypatch.chdir(tmp_path)
    yield
```

範例測試（`test_safety.py`，驗證安全宣稱與實作一致——review #1 的教訓）：

```python
"""safety.py gate 測試 —— 純邏輯，不觸 GUI。"""
from desktop_harness import safety


def test_sensitive_name_blocked():
    try:
        safety.check_app_allowed("1Password")
        assert False, "should raise"
    except PermissionError as e:
        assert "DH_ALLOW_SENSITIVE" in str(e)


def test_sensitive_bundle_blocked():
    try:
        safety.check_app_allowed("SomeApp", bundle_id="com.agilebits.onepassword")
        assert False, "should raise"
    except PermissionError:
        pass


def test_normal_app_allowed():
    safety.check_app_allowed("TextEdit")  # 不應拋


def test_allow_sensitive_escape_hatch(monkeypatch):
    monkeypatch.setenv("DH_ALLOW_SENSITIVE", "1")
    safety.check_app_allowed("1Password")  # 逃生口生效
```

## GitHub Actions workflow 範本（供日後採用；本提案不建立此檔）

**重要前提：** runner 上**沒有** Accessibility / Screen Recording 權限。`import Quartz` 可以（pyobjc 裝得上、import 不需要權限），但任何真的走 AX / CGEvent 的測試都會失敗或行為未定義——所以測試要嘛是純邏輯（`safety`、匹配排序），要嘛明確標 `@pytest.mark.macos_gui` 並在 CI 排除。

```yaml
# 建議檔名（本次不建立）：.github/workflows/quality.yml
name: quality

on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint-type:
    runs-on: ubuntu-latest   # ruff/mypy 不需要 macOS，省 runner 費
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pipx install ruff mypy
      - name: lint
        run: ruff check src scripts tests
      - name: format check
        run: ruff format --check src scripts tests
      - name: type check
        run: mypy

  test:
    runs-on: macos-latest     # pyobjc 只在 macOS 可 import
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e . pytest pytest-cov
      - name: unit tests (sandboxed, no GUI permissions needed)
        run: pytest -m "not macos_gui" --cov=desktop_harness --cov-report=term --cov-report=xml
        env:
          DH_NO_DAEMON: "1"
      - name: upload coverage report (no threshold yet — report only)
        uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: coverage.xml
```

## 拆分選項（若日後嫌單 job 訊號不清）

把 `lint-type` 與 `test` 拆開已是範本現況；更進一步可拆 `lint` / `type` / `test` 三個 job，但每個都是獨立 runner 啟動成本。**保守建議：先維持現狀，痛了再拆。**

## 未來（非本次範圍）

- 覆蓋率門檻：等 `tests/` 涵蓋 `safety.py`、`windows.find_app`、`run.py` 的 CLI 解析後，再設初始門檻（建議從 30% 起步，只升不降，用 ratchet 檔案鎖住）。
- `macos_gui` 標記的測試可另立**手動觸發**（`workflow_dispatch`）的 workflow，在有自架 macOS runner（具權限）時啟用——雲端 runner 不考慮。
