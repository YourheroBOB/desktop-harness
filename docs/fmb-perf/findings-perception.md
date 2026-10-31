# Findings — 視窗／截圖路徑（`windows.py`、`capture.py`、`admin.py`）

---

## PERC-1（P1）`find_app` 每次做完整 NSWorkspace 列舉；`activate` 輪詢每 80ms 一次全列舉

**位置：**
- `windows.find_app()` — 每次呼叫都執行 `list_apps()`（遍歷 `NSWorkspace.sharedWorkspace().runningApplications()` 並排序）。
- `windows.activate()` — 冷啟動確認迴圈：`deadline = time.time() + 4.0`、`time.sleep(0.08)` → 最多 ~50 次 `find_app` = **~50 次完整 NSWorkspace 列舉 + Python 排序**；焦點確認迴圈（1.2s、80ms 間隔）再加 ~15 次。

**影響：**
- `activate` 是幾乎每個 agent 任務的第一步，冷啟動時這兩個迴圈佔掉可觀時間（每次列舉雖然只需數 ms，但 ×65 次加上 sleep 佔了 4 秒預算的大半 CPU）。
- 焦點戰爭情境（agent host 搶焦點，selftest 已觀察到此情況）下，每輪都重複「全列舉 → 找 app → 檢查 active → 再 activate」。
- `find_app` 也是 `click_text` 等 helper 的熱路徑（`helpers.py` 未審，待確認呼叫頻率）。

**建議修法：**
1. `activate` 的兩個輪詢迴圈不要用 `find_app`（名稱→重新列舉），改用已解析到的 **pid**：
   ```python
   app = NSRunningApplication.runningApplicationWithProcessIdentifier_(app_info["pid"])
   if app and app.isActive():
       break
   ```
   單一 pid 查詢遠便宜於全列舉。
2. 若仍需名稱解析路徑：在模組層加一個極短 TTL 的 `list_apps()` 結果快取（100–200ms，daemon 常駐行程內效益最大）：
   ```python
   _APPS_CACHE: tuple[float, list] = (0.0, [])
   def list_apps(max_age: float = 0.15) -> list[dict]:
       ts, cached = _APPS_CACHE
       now = time.monotonic()
       if now - ts < max_age:
           return cached
       ...  # 原邏輯；寫回 _APPS_CACHE（注意：呼叫端可能修改 list，回傳副本或 tuple of dicts）
   ```
   注意回傳可變 list 的快取要防呼叫端污染 —— 保守做法是回傳 `list(cached)`（淺拷貝）。

**驗證方式：** 計時測試（不需 GUI 斷言）：連續呼叫 `list_apps()` 1000 次量測前後耗時差；`activate` 輪詢部分以 fake `NSRunningApplication`（或 monkeypatch `runningApplicationWithProcessIdentifier_`）驗證迴圈不再呼叫 `list_apps`。本機 Mac 上執行，讀取性操作，無風險。

**優先級：** P1

---

## PERC-2（P1）`capture.screenshot` 每次全量列舉視窗 + 子字串 first-hit 匹配

**位置：** `capture.screenshot()` — `if wid is None and app:` 分支：遍歷 `winmod.list_windows()`（`CGWindowListCopyWindowInfo` 全量）並以 `app.lower() in w["app"].lower() or ... in w["title"]` **first-hit** 取第一個匹配。

**影響：**
- 每張截圖都付一次全視窗列舉；observe loop（24 張/輪）與 fallback 視覺路徑會放大成本。
- First-hit 子字串：多視窗 app（例如同時開 3 個 Safari 視窗）截到哪一個取決於 `CGWindowList` 順序，不可預期 —— 對「`verify()` 後讀圖判斷」的流程是正確性風險（截錯視窗 → 誤判）。
- `window_info()` 有同樣的 first-hit 問題。

**建議修法：**
1. 優先以 **pid** 匹配（呼叫端若來自 `find_app`/`frontmost_app` 已有 pid）：
   ```python
   def _match_window(app: str | None, pid: int | None):
       wins = winmod.list_windows()
       if pid is not None:
           exact = [w for w in wins if w["pid"] == pid]
           if exact:
               return exact[0]
       if app:
           # exact name 優先，其次 title 子字串；多於一個時回傳清單或挑最上層（y 最小/最近聚焦）
   ```
2. `screenshot()` 增加可選 `pid` 參數，並把匹配邏輯集中為一個可單測的純函式（輸入 window dict list + 查詢 → 輸出 window），用 fake 資料測排序優先級。
3. `list_windows()` 同樣可加 100ms 級 TTL 快取（與 PERC-1 共用模式）。

**驗證方式：** 純函式單測（fake window list：多個同 app 不同 pid 的視窗、名稱子字響應）斷言匹配優先級：pid > exact name > title 子字串。實機驗證：開兩個同 app 視窗，指定 pid 截圖後比對兩張 PNG 差異。截圖寫到 `tmp_path`。

**優先級：** P1

---

## PERC-3（P1）`TMP` 截圖檔永不清理 — 磁碟資源洩漏

**位置：** `capture.py` — `TMP = Path(tempfile.gettempdir()) / "desktop-harness"`；`screenshot()` 產生 `capture-{pid}-{time_ns()}.png` 後**從不刪除**。

**影響：**
- 每張全螢幕 PNG 數 MB；`verify()` 每次動作後一張、observe loop 24 張/輪、daemon 長跑數天的 agent session —— 洩漏量級可到 GB。
- 唯一被清理的時機是手動刪或系統重開機清 `/tmp`（macOS 定期清理行為不保證、不即時）。
- 檔名唯一化（per-call unique）是先前修對的（PRE-RELEASE-REVIEW #17），但只解決了 clobber，沒解紹累積。

**建議修法：** 在 `screenshot()` 寫檔前做一次輕量清理（节流：每 N 次呼叫或每 60s 一次，避免每次都掃目錄）：
```python
def _sweep_old_captures(max_files: int = 200, max_age_days: float = 2.0) -> None:
    try:
        files = [p for p in TMP.glob("capture-*.png")]
        # 1) 逾齡刪除；2) 超量時最舊先刪
    except OSError:
        pass  # 清理失敗不影響主流程
```
**保守邊界：只刪 `capture-*.png` 自家命名模式的檔案**，絕不刪目錄中其他檔案；`path=` 參數指定的外部路徑一律不動。同樣模式套用到 doctor 的 `dh-doctor.png`。

**驗證方式：** 單測（`tmp_path`）：預先放 300 個假 `capture-*.png`（部分 mtime 調舊）+ 幾個不相關檔案 → 呼叫 sweep → 斷言：舊檔與超量檔被刪、不相關檔案完好、上限內的新檔保留。不寫 repo、不動真實 `/tmp/desktop-harness`（測試用 monkeypatch TMP）。

**優先級：** **P1**（長跑必漏，修法便宜）

---

## PERC-4（P2）doctor 寫固定路徑 `dh-doctor.png`，併發執行互相覆蓋

**位置：** `admin.run_doctor()` — `cap.screenshot(path=Path(tempfile.gettempdir()) / "dh-doctor.png")`。

**影響：** 兩個終端同時跑 `--doctor`（或 agent 與人類同時跑）互相覆蓋；只影響 doctor 自身的 size 檢查讀到別人剛寫入的檔（同為 PNG，通常仍 PASS）—— 低實害、高噁心度。

**建議修法：** 沿用 `capture.screenshot()` 的 unique 命名（不傳 `path`，讓它生成 `capture-{pid}-{ns}.png`），doctor 讀完 `stat` 後刪掉；或 `tempfile.NamedTemporaryFile(suffix=".png", delete=False)`。

**驗證方式：** 並發兩個 doctor 子進程（沙箱 TMP），斷言兩者都 PASS 且無共享檔案寫入衝突。

**優先級：** P2

---

## PERC-5（P2）`activate` 焦點確認採忙等輪詢 + 重複 `activateWithOptions_`

**位置：** `windows.activate()` 尾段 — 1.2s deadline 內每 80ms 重送 `activateWithOptions_(1 << 1)`，與搶焦點的 agent host 互毆。

**影響：** 功能上可行（selftest 已依賴它），但：(a) 每輪重送 activate 是系統級 focus 事件噪音；(b) 忙等佔 CPU；(c) 1.2s 用盡時 audit 記 `focus_uncertain`，呼叫端無結構化方式知道「啟動成功但焦點失敗」與「啟動失敗」的差別。

**建議修法：**
1. 改事件驅動：註冊 `NSWorkspaceDidActivateApplicationNotification` 觀察（在 daemon 常駐行程中效益最大，可直接收到「目標 app 已 active」通知再返回）；in-process 一次性路徑保留輪詢但拉長間隔（80ms → 120ms）。
2. 回傳值增加 `focus_confirmed: bool` 欄位，讓 audit／呼叫端可分辨。
3. **保守**：若不想動通知機制，至少把「重送 activate」改為「僅在觀察到 active 變 false 時才重送」，避免無腦連發。

**驗證方式：** 事件版本可用 fake notification center 單測回傳時序；實機驗證照 selftest 的 TextEdit 流程（已有現成 harness），比較修改前後 `activate` 的平均耗時（selftest 已印每項 ms，直接可用）。

**優先級：** P2（等 PERC-1 的 pid 直查先落地，輪詢成本已大降）

---

## 與未審檔案的交叉參考（待確認，不重複展開）

- `helpers.click_text`／`find`／`ensure_media_playing` 的重複 AX walk（PRE-RELEASE-REVIEW #9）：修法方向（短 TTL snapshot 快取、`click_text` 重用 `find` 的節點做 miss 樣本）仍然成立，但實作細節需先審 `ax.py`／`helpers.py`。**建議作為下一輪審查的第一批檔案。**
- `input.py` 固定 settle sleeps（PRE-RELEASE-REVIEW #13）：同上，待審。
