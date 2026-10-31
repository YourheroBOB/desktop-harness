# 批次 1：capture/windows 視窗匹配去重 + 模組層副作用移除

- **範圍：** `src/desktop_harness/windows.py`（新增 `find_window`）、`src/desktop_harness/capture.py`
- **風險：** 低
- **對應 findings：** D1、C1、C3（TMP）、N1、N3
- **行為變更：** 視窗匹配由「first-hit substring」改為「exact > substring」（明確化優先級，見下方說明）；`window_info()` 行為**保持不變**

## 1. 重構前問題

### 1.1 兩處各自實作匹配（D1 / C1）

`screenshot()` 內：

```python
if wid is None and app:
    for w in winmod.list_windows():
        if app.lower() in w["app"].lower() or app.lower() in (w["title"] or "").lower():
            wid = w["id"]
            break
    if wid is None:
        raise RuntimeError(f"no on-screen window for app={app!r}")
```

`window_info()` 內（只匹配 app 名、不匹配 title — 與上者的差異完全隱晦）：

```python
def window_info(app: str | None = None) -> dict[str, Any] | None:
    if app:
        for w in winmod.list_windows():
            if app.lower() in w["app"].lower():
                return w
        return None
    wins = winmod.list_windows()
    return wins[0] if wins else None
```

問題：

- 匹配策略是 **first-hit substring**，與 `windows.find_app` 已改良的「精確 > 前綴 > 子字串」排序（ADR-0007 之後的基準）不一致；`screenshot("Text")` 可能拍到第一個名字含 "text" 的視窗。
- `capture` 直接消費 `list_windows()` 的 dict 鍵形狀；windows 若改回傳結構，capture 兩處一起壞。

### 1.2 模組層副作用（C3）

```python
TMP = Path(tempfile.gettempdir()) / "desktop-harness"
TMP.mkdir(exist_ok=True)   # import 即 mkdir
```

### 1.3 魔術數字與未使用 import（N3）

```python
data = rep.representationUsingType_properties_(
    4, None)  # NSBitmapImageFileTypePNG = 4
```

`from AppKit import NSBitmapImageRep, NSImage` 中的 `NSImage` 從未使用。

## 2. 需先補的測試（動手前）

新增單元測試（純函式層級，monkeypatch `list_windows` 回傳假資料，**不需要** pyobjc／真實視窗）：

1. `find_window`：exact 命中優先於 substring（假清單含 `["TextEdit", "TextExpander"]`，查 `"TextEdit"` 必須回傳前者，即使後者在列表較前）。
2. `find_window`：title 匹配（app 名不含、title 含 → 有 `match_title=True` 時命中，`False` 時回 `None`）。
3. `find_window`：查無 → `None`；空字串 → `None`。
4. 特徵測試釘住 `window_info` 現況：只匹配 app 名、不匹配 title（重構後必須仍綠）。
5. `capture._save_cgimage`：魔術數字改常數前後產出相同 PNG bytes（用一張假 CGImage 或跳過平台相依部分，至少以常數值 `NSBitmapImageFileTypePNG == 4` 斷言）。

測試隔離：沿用 fmb-perf 原則 — 一律 `tmp_path`、`DH_NO_DAEMON=1`、不碰使用者環境。

## 3. 重構步驟

1. 補上節測試並確認全綠（此時尚未改任何產品碼）。
2. `windows.py` 新增 `find_window()`（唯一新增的公開函式）。
3. `capture.screenshot()` 的匹配迴圈改為委託 `find_window`（含 title 匹配，**保持**原本「app 名或 title」語意）。
4. `capture.window_info()` 改為 `find_window(app, match_title=False)`（保持只匹配 app 名）。
5. `capture.TMP` 改為 `_capture_dir()` 惰性函式（見下），`screenshot` 內改呼叫。
6. `NSBitmapImageFileTypePNG` 取代魔術數字；移除未使用的 `NSImage` import；`winmod`／`_safety` 別名改為完整名稱（N1）。
7. 跑全部測試 + `desktop-harness --doctor` + 一張手動截圖煙霧。

## 4. 重構前後對照

### 4.1 `windows.py` 新增（重構後）

```python
def find_window(app: str, *, match_title: bool = True) -> dict[str, Any] | None:
    """Find an on-screen window by app name: exact > substring.

    match_title=True also accepts a substring hit on the window title
    (kept for screenshot()'s app-or-title semantics). Returns None if
    nothing matches. Mirrors find_app's exact-first policy (ADR-0007).
    """
    q = (app or "").strip().lower()
    if not q:
        return None
    exact: dict[str, Any] | None = None
    sub: dict[str, Any] | None = None
    for w in list_windows():
        name = (w.get("app") or "").lower()
        if name == q:
            exact = w
            break
        if sub is None and q in name:
            sub = w
        elif sub is None and match_title and q in (w.get("title") or "").lower():
            sub = w
    return exact or sub
```

### 4.2 `capture.screenshot()` 匹配段

重構前：

```python
if wid is None and app:
    for w in winmod.list_windows():
        if app.lower() in w["app"].lower() or app.lower() in (w["title"] or "").lower():
            wid = w["id"]
            break
    if wid is None:
        raise RuntimeError(f"no on-screen window for app={app!r}")
```

重構後：

```python
if wid is None and app:
    w = windows.find_window(app)   # exact > substring; app name or title
    if w is None:
        raise RuntimeError(f"no on-screen window for app={app!r}")
    wid = w["id"]
```

### 4.3 `capture.window_info()`

重構後：

```python
def window_info(app: str | None = None) -> dict[str, Any] | None:
    if app:
        # 原行為：只匹配 app 名，不匹配 title — 以 match_title=False 保持
        return windows.find_window(app, match_title=False)
    wins = windows.list_windows()
    return wins[0] if wins else None
```

### 4.4 TMP 惰性化

重構前：

```python
TMP = Path(tempfile.gettempdir()) / "desktop-harness"
TMP.mkdir(exist_ok=True)
```

重構後：

```python
_TMP_DEFAULT = Path(tempfile.gettempdir()) / "desktop-harness"

def _capture_dir() -> Path:
    """Lazily create the capture dir — no mkdir at import time (testability)."""
    _TMP_DEFAULT.mkdir(parents=True, exist_ok=True)
    return _TMP_DEFAULT
```

> 注意：`docs/fmb-perf/verification-plan.md` 提到以 monkeypatch `capture.TMP` 做測試隔離。改成函式後請同步改為 monkeypatch `capture._capture_dir` 或 `capture._TMP_DEFAULT`（該文件為建議性質，屆時在 PR 內附註即可）。**刻意不**新增 `DH_CAPTURE_DIR` 環境變數 — 保持行為面最小變更（如需要，由 fmb-perf PERC-3 修復 PR 一併考慮清理策略時再議）。

### 4.5 常數化

重構後：

```python
from AppKit import NSBitmapImageFileTypePNG, NSBitmapImageRep

data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
```

## 5. 驗證方式（本批獨立驗收）

1. 新增單元測試全綠（含 `window_info` 特徵測試）。
2. `desktop-harness --doctor` 全 PASS（doctor 內部走 `capture.screenshot`）。
3. `desktop-harness selftest` 全 PASS。
4. 手動煙霧：`desktop-harness <<'PY' print(screenshot("TextEdit")) PY` — 檔名唯一、路徑在 `$TMPDIR/desktop-harness/`。

## 6. 風險與回滾

- **行為變更點只有一處**：匹配從 first-hit substring 改為 exact 優先。風險是某些依賴「湊巧第一個 substring 命中」的腳本會改拍到別的視窗 — 但這正是 review #7 對 `find_app` 的同一批評，方向一致。若要極端保守，第一步可只做去重（`find_window` 內部先維持 first-hit substring），第二步再改優先級；兩步都在本批內，各自有測試。
- 回滾：單一 PR revert 即可，無資料遷移、無介面相容問題（`window_info` 與 `screenshot` 簽名不變）。
- PERC-3（截圖檔永不清理）**不在本批修**，只把目錄存取集中到 `_capture_dir()`，讓後續清理 PR 有單一施力點。
