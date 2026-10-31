# 批次 3：`admin.run_doctor` 資料驅動化

- **範圍：** `src/desktop_harness/admin.py`（僅此一檔）
- **風險：** 低
- **對應 findings：** D3、L1、N5
- **行為變更：** doctor 的截圖輸出從固定檔名 `dh-doctor.png` 改為唯一檔名並於檢查後刪除（PERC-4；輸出文字不變）

## 1. 重構前問題

`run_doctor()` 約 75 行，五個檢查項各自內嵌一個 `try/except → check()` 樣板：

```python
# Screen Recording — try a tiny capture
try:
    from . import capture as cap
    path = cap.screenshot(path=Path(tempfile.gettempdir()) / "dh-doctor.png")
    size = Path(path).stat().st_size
    check("Screen Recording (window/display capture)", size > 1000,
          f"{size} bytes" if size > 1000 else "empty capture — grant Screen Recording")
except Exception as e:
    check("Screen Recording (window/display capture)", False, str(e))
```

（同型樣板重複五次；`AXIsProcessTrusted` 被 import 兩次。）問題：

- 加第六個檢查 = 在函式體內再塞一個 try/except 區塊，檢查之間無法單獨測試。
- pyobjc 失敗是**致命早退**，其他失敗只是計數 — 這個控制流藏在函式中段，資料驅動化後顯式化。
- 固定檔名 `dh-doctor.png`：兩個 doctor 併發跑會互相覆蓋（PERC-4），且與 `capture.screenshot` 的唯一命名策略（review #17 修正）不一致（N5）。

## 2. 需先補的測試（動手前）

1. 特徵測試：以假的 `sys.stdout` 捕獲 `run_doctor()` 輸出，斷言五個檢查名稱與順序、`PASS/FAIL` 格式、結尾摘要格式完全不變（monkeypatch 各 `_check_*` 函式回傳固定值，**不**需要真實權限）。
2. 致命路徑：monkeypatch pyobjc 檢查丟例外 → 印出 install 提示後回傳 1 且**不**執行後續檢查。
3. 檔名唯一性：跑兩次 doctor（monkeypatch capture），斷言兩次用的暫存路徑不同、檢查結束後檔案不存在（清理生效）。

## 3. 重構步驟

1. 補 §2 測試。
2. 每個檢查抽成 module-level `_check_xxx() -> tuple[bool, str]` 私有函式（丟例外 = FAIL + 訊息，由框架統一捕捉）。
3. `run_doctor()` 改為檢查表驅動 + 一個共用的執行迴圈；pyobjc 檢查標記 `fatal=True`。
4. doctor 暫存截圖改唯一檔名（`dh-doctor-<pid>-<ns>.png`）並在大小檢查後 `unlink(missing_ok=True)`。
5. 移除重複的 `AXIsProcessTrusted` import（第二處）。
6. 全測試綠 + 實機 `--doctor` 全 PASS。

## 4. 重構前後對照

### 4.1 檢查函式（重構後，以 Screen Recording 為例）

```python
def _check_screen_recording() -> tuple[bool, str]:
    from . import capture as cap
    path = cap.screenshot(
        path=Path(tempfile.gettempdir())
        / f"dh-doctor-{os.getpid()}-{time.time_ns()}.png"   # PERC-4: 唯一檔名
    )
    size = Path(path).stat().st_size
    Path(path).unlink(missing_ok=True)   # doctor 不留暫存檔
    return (
        size > 1000,
        f"{size} bytes" if size > 1000 else "empty capture — grant Screen Recording",
    )
```

### 4.2 `run_doctor()` 主體

重構後：

```python
_DOCTOR_CHECKS: tuple[tuple[str, Callable[[], tuple[bool, str]], bool], ...] = (
    # (顯示名稱, 檢查函式, 是否致命)
    ("pyobjc frameworks (Quartz, AppKit, ApplicationServices)",
     _check_pyobjc, True),
    ("Accessibility permission (AX + input)",
     _check_accessibility, False),
    ("Screen Recording (window/display capture)",
     _check_screen_recording, False),
    ("AX snapshot (frontmost app)",
     _check_ax_snapshot, False),
    ("window list",
     _check_window_list, False),
)


def run_doctor() -> int:
    print("desktop-harness doctor\n")
    fails = 0
    for name, fn, fatal in _DOCTOR_CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, str(e)
        status = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail else ""
        print(f"  [{status}] {name}{extra}")
        if not ok:
            fails += 1
            if fatal:
                print("\ninstall deps in the project venv, then re-run --doctor")
                return 1
    # …（既有結尾摘要與 pane 提示，逐字保留）
```

> 注意事項：(1) `_DOCTOR_CHECKS` 在 module level 定義會在 import 時求值各函式名 — 函式定義需在表之前，或改在 `run_doctor()` 內組表；實作時以「表在函式內組、元素為 module-level 檢查函式」最單純。(2) `_check_accessibility` 回傳的 detail 文字（System Settings 指引）必須與現況逐字相同，由 §2.1 的輸出特徵測試保證。

## 5. 驗證方式（本批獨立驗收）

1. §2 測試全綠。
2. 實機 `desktop-harness --doctor`：輸出與重構前 diff **應為空**（唯一允許差異：無 — 暫存檔名不出現在輸出）。
3. 併發跑兩個 doctor（`&` 背景一個），皆正常完成、互不覆蓋。

## 6. 風險與回滾

- 風險最低的一批：輸出格式以特徵測試逐字釘住，唯一的實際變更（唯一檔名 + 清理）是 fmb-perf 已列的改善項。
- 回滾：單一 PR revert。
- **明確不做**：doctor 檢查項目的增減、`len(nodes) > 0` 語意（review #21 已在 v0.4.2 修好，保持）、AX 快照上限調整。
