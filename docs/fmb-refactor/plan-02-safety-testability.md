# 批次 2：safety 模組測試化與死 API 誠實化

- **範圍：** `src/desktop_harness/safety.py`（僅此一檔）
- **風險：** 低
- **對應 findings：** D2、C3（`_AUDIT` import 時讀 env）、C2（僅補註解與測試，不做結構性改動）、N2
- **行為變更：** `DH_AUDIT_LOG` 由「import 時」改為「每次寫入時」讀取（見 §4.3，此為刻意且必要的可測性變更）

## 1. 重構前問題

### 1.1 模組層 env 副作用（C3）

```python
_AUDIT = Path(os.environ.get(
    "DH_AUDIT_LOG",
    Path.home() / ".desktop-harness" / "audit.jsonl",
))
```

測試想把 audit log 導向 `tmp_path`，必須在 `import safety` **之前**設好環境變數（或 `importlib.reload`），與 pytest 的 fixture 順序耦合，是目前安全模組幾乎沒有單元測試的主因之一。

### 1.2 敏感清單重複（D2）

兩個 tuple 有 8 項完全重疊（bundle 清單 = name 清單去掉 `secrets`/`wallet`/`bank`）。新增密碼管理器要記得改兩處；漏改一處就是安全缺口（review #1 曾要求擴充清單，此結構會讓擴充容易出錯）。

### 1.3 死 API（N2）

`check_helper_allowed()` 從未被任何程式碼呼叫，阻擋清單以區域變數內嵌。ROADMAP #6 給了兩個處置選項：(a) 移除並改文件；(b) 保留為未來 hook。**本計畫採 (b) 保守路線**：保留公開函式（避免破壞潛在外部使用者／agent-workspace 呼叫），但把清單提為模組常數、docstring 明言現況，消除「已接線」的誤導。

### 1.4 循環依賴迴避的惰性 import（C2）

`check_frontmost_allowed()` 內 `from . import windows as winmod`。本批**不改結構**（集中 gate 機制影響面大，另案評估），只補測試與註解把它釘住。

## 2. 需先補的測試（動手前）

1. `_looks_sensitive()` 純函式測試：name 命中、bundle 命中、兩者皆空、大小寫不敏感、`"bank"` 只在 name 清單（`_looks_sensitive("MyBankApp")` → True；`_looks_sensitive("", "com.mybankapp.x")` → False，釘住 name-only 差異）。
2. `check_app_allowed()`：敏感名稱 → `PermissionError` 且訊息含 `DH_ALLOW_SENSITIVE` 提示；`allow_sensitive()` 環境覆寫後放行。
3. `check_frontmost_allowed()`：monkeypatch `windows.frontmost_app` 回傳敏感／非敏感／丟例外三種情況（例外 → 靜默放行，釘住現有「fail-open」行為 — 這是既有設計，重構不得改變；若要改 fail-closed 屬安全決策，需 BOB 拍板，不在本批）。
4. `audit()`：以 `DH_AUDIT_LOG` 指向 `tmp_path`，斷言 JSONL 一行、欄位齊全；**並補一條「import 後才設 env 也能生效」的測試** — 這條在重構前會失敗，正是本批要修的目標（TDD 釘法）。

## 3. 重構步驟

1. 補 §2 測試（audit 那條預期失敗，其餘應綠）。
2. `_AUDIT` 常數 → `_audit_path()` 函式；`audit()` 改呼叫。
3. 敏感清單以「基底 tuple + name 額外項」表達。
4. `check_helper_allowed()` 的清單提為模組常數 `_BLOCKED_HELPERS`，補誠實 docstring。
5. `check_frontmost_allowed()` 補註解說明惰性 import 原因（循環依賴）與 fail-open 語意。
6. 全測試綠 + `selftest`（selftest 會跑 audit 路徑）。

## 4. 重構前後對照

### 4.1 敏感清單（D2）

重構前：

```python
_SENSITIVE_NAME_SUBSTR = (
    "1password", "bitwarden", "keychain", "lastpass", "keepass",
    "dashlane", "nordpass", "enpass", "secrets", "wallet", "bank",
)
_SENSITIVE_BUNDLE_SUBSTR = (
    "1password", "bitwarden", "keychain", "lastpass", "keepass",
    "dashlane", "nordpass", "enpass",
)
```

重構後：

```python
# bundle id 比顯示名稱精確，先列基底；顯示名稱另有三個較寬的子字串
# （"secrets"/"wallet"/"bank" 對 bundle id 誤傷率過高，僅用於 name 比對 —
#  見 docs/fmb-adr/ADR-0008.md 的 substring 取捨）。
_SENSITIVE_BUNDLE_SUBSTR = (
    "1password", "bitwarden", "keychain", "lastpass", "keepass",
    "dashlane", "nordpass", "enpass",
)
_SENSITIVE_NAME_SUBSTR = _SENSITIVE_BUNDLE_SUBSTR + ("secrets", "wallet", "bank")
```

### 4.2 audit 路徑惰性化（C3）

重構前：

```python
_AUDIT = Path(os.environ.get(
    "DH_AUDIT_LOG",
    Path.home() / ".desktop-harness" / "audit.jsonl",
))
...
def audit(event: str, detail: dict[str, Any] | None = None) -> None:
    try:
        _AUDIT.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(), "event": event, "detail": detail or {}}
        with _AUDIT.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass
```

重構後：

```python
def _audit_path() -> Path:
    """Resolve at call time, not import time — lets tests point
    DH_AUDIT_LOG at a tmp_path after import (and matches how daemon
    resolves DH_SOCKET / DH_TOKEN_PATH per call)."""
    return Path(os.environ.get(
        "DH_AUDIT_LOG",
        Path.home() / ".desktop-harness" / "audit.jsonl",
    ))


def audit(event: str, detail: dict[str, Any] | None = None) -> None:
    # 靜默吞例外是既有行為（fail-open，見 docs/fmb-perf TR-4）；
    # 改為警告輸出屬行為修復，刻意不在本重構批處理。
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(), "event": event, "detail": detail or {}}
        with path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass
```

### 4.3 死 API 誠實化（N2）

重構後：

```python
# 未接線的未來 hook：核心套件刻意不內建任何 shell escape helper
# （docs/fmb-adr/ADR-0003.md），因此這個函式目前沒有任何呼叫者。
# 若未來新增 run_shell 類 helper，必須在其進入點呼叫本函式。
_BLOCKED_HELPERS = frozenset({"run_shell", "shell", "osascript_raw"})


def check_helper_allowed(name: str) -> None:
    """Reserved gate for future high-risk helpers (not wired today).

    SECURITY.md must not claim safe-mode blocks anything concrete
    beyond sensitive-app name/frontmost/screenshot gates (ADR-0008).
    """
    if name in _BLOCKED_HELPERS and safe_mode() and not allow_sensitive():
        raise PermissionError(
            f"helper {name!r} blocked in safe mode (DH_SAFE=1)."
        )
```

## 5. 驗證方式（本批獨立驗收）

1. §2 單元測試全綠（含原本會失敗的「import 後設 env」測試）。
2. `DH_AUDIT_LOG=<tmp>/a.jsonl desktop-harness selftest` — audit 寫到指定路徑。
3. `open_app` 敏感阻擋煙霧不變：`desktop-harness <<'PY' open_app("1Password") PY` 仍拒絕。
4. 行為差異清單只有一項：程式生命週期內**中途**改 `DH_AUDIT_LOG` 環境變數會開始生效（原本 import 後固定）。對 CLI 短生命週期行程無影響；對 daemon 長行程，這反而與 fmb-perf 對 `DH_SOCKET` 的「per-call 解析」建議方向一致。

## 6. 風險與回滾

- 主要風險是 audit 惰性化改變了 env 讀取時點 — 已在 §5.4 明列，且是往「可測試」方向收斂。
- 敏感清單合併為純結構表達，內容逐一相等（以測試斷言兩個清單的成員集合與重構前一致）。
- gate 行為零變更（fail-open、阻擋訊息、覆寫語意全數以測試釘住）。
- 回滾：單一 PR revert。
- **明確不做**：audit 輪替、靜默吞例外改警告（TR-4）、fail-open 改 fail-closed、敏感清單改 bundle id 精確匹配（ROADMAP #6 的另一子項）— 這些都是行為變更，另案處理。
