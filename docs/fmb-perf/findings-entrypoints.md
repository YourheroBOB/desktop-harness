# desktop-harness 效能與可靠性審查：進入點與腳本層發現

- **日期：** 2026-08（補充審查）
- **範圍：** `scripts/voice_session.py`、`scripts/observe-demo.sh`、`src/desktop_harness/demo.py` 及相關文件描述
- **repo：** YourheroBOB/desktop-harness @ v0.4.2
- **性質：** 僅新增文件，未修改任何原始碼。所有建議均為提案。
- **前置閱讀：** 本文件補充 `findings-daemon.md`、`findings-timeouts-recovery.md`、`findings-observability.md` 未涵蓋的「進入點／腳本層」細節。

---

## 優先級定義

| 級別 | 定義 |
|------|------|
| **P0** | 會讓主要功能整體失效、掛死、或單一事件可讓程式崩潰 — 應優先修 |
| **P1** | 明顯的效能損失、資源洩漏、或可靠性缺口 — 排入近期迭代 |
| **P2** | 打磨項：可觀測性、邊界情況、測試隔離 — 有空就做 |

---

## 發現總表

| ID | 領域 | 標題 | 優先級 |
|----|------|------|--------|
| ENTRY-1 | 逾時 | `voice_session.py` WebSocket 連線無 `open_timeout`、事件迴圈無 idle timeout | P1 |
| ENTRY-2 | 併發 | voice tool `execute()` 同步阻塞 asyncio 事件迴圈 | P1 |
| ENTRY-3 | 重試 | 無連線重試／退避機制；斷線即結束 | P1 |
| ENTRY-4 | 競態 | `demo.py` 固定 `time.sleep` 在慢／快機器上分別競態與浪費 | P2 |
| ENTRY-5 | 錯誤恢復 | `demo.py` 無步驟錯誤處理；失敗時仍繼續後續動作 | P2 |
| ENTRY-6 | 可觀測性 | voice session 事件僅 `print()`，無結構化日誌與錯誤分類 | P2 |
| ENTRY-7 | 重試 | `response.done` + `pending_calls` 自動續 turn 無上限 | P2 |
| ENTRY-8 | 資源管理 | `observe-demo.sh` 預設寫入 repo 外固定路徑且無 trap 清理 | P2 |

---

## 詳細發現

### ENTRY-1：WebSocket 連線與事件迴圈缺乏逾時保護

- **位置：** `scripts/voice_session.py` → `run_session()` → `websockets.connect(...)` 與 `async for raw in ws`
- **現狀：**
  ```python
  async with websockets.connect(
      WS_URL,
      additional_headers=headers,
      max_size=8 * 1024 * 1024,
  ) as ws:
      ...
      async for raw in ws:
  ```
  連線建立未設定 `open_timeout`；`async for` 亦無 idle timeout。
- **影響：**
  - 網路中斷、防火牆靜默丟包、或 DNS 解析掛起時，`connect()` 可能無限等待。
  - 伺服器接受連線後停止推送（半開連接），`async for` 會永久阻塞，腳本無出口。
  - Agent 使用者會看到「卡住」的 voice session，無法區分是模型思考還是程式掛死。
- **建議修法：**
  1. 連線加上明確逾時：
     ```python
     async with websockets.connect(
         WS_URL,
         additional_headers=headers,
         max_size=8 * 1024 * 1024,
         open_timeout=5.0,
     ) as ws:
     ```
  2. 事件迴圈改用 `asyncio.wait_for` 包裹，或維護 `last_event_ts`，超過 idle 門檻（如 60s）主動 `await ws.close()` 並退出。
  3. 例外處理：`except asyncio.TimeoutError` 與 `except websockets.WebSocketException` 分別記錄並回傳非零 exit code。
- **驗證方式：**
  - 使用 mock WebSocket server（pytest + `tmp_path` + `localhost` ephemeral port 或 `unix socket`）：
    - Case A：server accept 後從不 send → 驗證腳本在 idle timeout 內退出。
    - Case B：TCP connect 成功但 TLS/HTTP upgrade 掛起 → 驗證 `open_timeout` 觸發。
  - 不連線 `wss://api.x.ai`；認證 header 使用 `FAKE_VALUE_FOR_TEST`。
- **優先級：** P1

### ENTRY-2：同步工具執行阻塞 asyncio 事件迴圈

- **位置：** `scripts/voice_session.py` → `run_session()` → `result = execute(name, arguments, dry_run=dry_run)`
- **現狀：** `execute()` 同步呼叫 desktop-harness helper（可能包含 AX walk、滑鼠動畫、截圖），在事件迴圈執行緒中直接執行。
- **影響：**
  - 單一工具執行可能耗時數百毫秒到數秒（如 `ensure_media_playing` 需多次 AX 走訪 + 等待）。
  - 阻塞期間 WebSocket 無法收送音訊串流，可能導致伺服端 VAD 逾時或 ping/pong 失敗而斷線。
  - 使用者感知為「語音回應延遲」或「聲音卡頓」。
- **建議修法：**
  - 將阻塞執行移出事件迴圈：
    ```python
    result = await asyncio.to_thread(execute, name, arguments, dry_run=dry_run)
    ```
  - **注意 AppKit main-thread 限制**（ADR-0006）：若 `execute()` 內部觸碰 AppKit（presence、capture），必須確認該執行緒模型是否相容。最保守做法是維持在單一 worker thread 序列執行，並在文件註明「voice session 期間不同時跑其他 AppKit 動作」。
  - 若無法安全背景化，至少在 `execute()` 前後發送 WebSocket ping 維持連線，並記錄阻塞耗時。
- **驗證方式：**
  - 單元測試：mock `execute()` 回傳前 `time.sleep(2.0)`，測量事件迴圈處理另一個協程任務的延遲（應接近 0）。
  - 整合測試（dry-run）：以 `--text` 模式執行，驗證音訊 delta 事件（或 mock 事件）在工具執行期間仍被處理。
- **優先級：** P1

### ENTRY-3：缺乏連線重試與退避機制

- **位置：** `scripts/voice_session.py` → `main()` → `asyncio.run(run_session(...))`
- **現狀：** 單次連線嘗試；任何 `websockets` 例外直接向上傳播，程式結束。
- **影響：**
  - 暫時性網路抖動、伺服器 502、或本機 DNS 延遲都會讓 voice session 直接退出。
  - 使用者必須手動重跑，體驗差。
- **建議修法：**
  1. 抽出 `connect_with_retry(url, headers, max_attempts=3)`：
     ```python
     for attempt in range(1, max_attempts + 1):
         try:
             return await websockets.connect(...)
         except (OSError, websockets.WebSocketException) as e:
             if attempt == max_attempts:
                 raise
             backoff = min(2 ** attempt, 8)
             print(f"connect failed ({e}); retry in {backoff}s", file=sys.stderr)
             await asyncio.sleep(backoff)
     ```
  2. 區分**可重試**（網路層、5xx）與**不可重試**（401/403 認證失敗、400 參數錯誤）——後者立即退出。
  3. 重試期間印出冷卻時間，避免使用者以為當機。
- **驗證方式：**
  - mock server：第 1、2 次拒絕連線（或立即 close），第 3 次成功。驗證退避序列為 2s、4s（或等比），且最終成功建立 session。
  - 認證失敗（mock 401）：驗證**不重試**，exit code 為 2。
- **優先級：** P1

### ENTRY-4：`demo.py` 固定 sleep 導致的競態與浪費

- **位置：** `src/desktop_harness/demo.py` → `time.sleep(0.4)`、`time.sleep(0.35)`、`time.sleep(0.6)`
- **現狀：** 以固定睡眠等待 TextEdit 開啟、新文件建立、打字完成。
- **影響：**
  - **慢機器／重負載：** TextEdit 未 ready 就 `list_windows()`、移動滑鼠、打字，可能點到錯誤位置或打字到其他 app。
  - **快機器：** 無謂等待，拖長 demo 時間。
- **建議修法：**
  - 改為條件等待（待 `helpers.wait_for` 落地後可直接使用；過渡期可在 `demo.py` 內部實作小型輪詢）：
    ```python
    def _wait_until(pred, timeout=5.0, poll=0.1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if pred():
                return True
            time.sleep(poll)
        return False
    ```
  - 對 TextEdit 視窗出現、新文件視窗 bounds、打字後內容驗證分別加入條件等待。
- **驗證方式：**
  - 在 CI（macOS runner）以 `time desktop-harness demo` 測量端到端時間；與修改前比較。
  - 以 `nice -n 20` 或背景負載模擬慢機器，驗證不再出現「no TextEdit window bounds」或打字到錯誤 app。
- **優先級：** P2

### ENTRY-5：`demo.py` 缺乏錯誤恢復與明確失敗路徑

- **位置：** `src/desktop_harness/demo.py` → `run_demo()`
- **現狀：** 未檢查 `H.open_app("TextEdit")` 是否成功；若失敗仍繼續移動滑鼠與打字；無 try/finally 確保 `hide_agent_presence()` 被呼叫。
- **影響：**
  - TextEdit 開啟失敗時，滑鼠移動與打字可能作用於當前前景 app（誤操作）。
  - 例外拋出時 presence overlay（藍色光環、橫幅）殘留螢幕上，造成「Agent active」誤導。
- **建議修法：**
  1. 包裝為：
     ```python
     try:
         H.enable_agent_cursor(True)
         if not H.open_app("TextEdit"):
             raise RuntimeError("TextEdit open_app returned falsy")
         if not _wait_until(lambda: any(w["app"] == "TextEdit" for w in H.list_windows())):
             raise RuntimeError("TextEdit window did not appear")
         ...
     finally:
         H.hide_agent_presence()
     ```
  2. 每一步失敗時印出清楚原因與當前前景 app，方便 agent／使用者判斷。
- **驗證方式：**
  - 單元測試：mock `H.open_app` 回傳 `None`/`False`，驗證 `hide_agent_presence()` 仍被呼叫且 exit code 非零。
  - 手動測試：在無 TextEdit 權限時執行 demo，確認不會誤打字到其他 app。
- **優先級：** P2

### ENTRY-6：voice session 缺乏結構化日誌與錯誤分類

- **位置：** `scripts/voice_session.py` → 多處 `print()`
- **現狀：** 連線狀態、工具呼叫、錯誤均以 `print()` 輸出，無時間戳、無等級、無模組名稱。
- **影響：**
  - 無法事後分析「哪一步慢」「哪類錯誤頻繁发生」。
  - 與 daemon 的 audit log、selftest 的計時輸出格式不一致，難以整合 observability stack。
- **建議修法：**
  1. 引入標準 `logging`：
     ```python
     import logging
     log = logging.getLogger("voice_session")
     logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
     ```
  2. 事件分類：
     - `connect_start` / `connect_ok` / `connect_retry` / `connect_fail`
     - `tool_execute_start` / `tool_execute_end`（含 `duration_ms`、`tool_name`、`ok`）
     - `turn_complete` / `turn_limit_reached`
  3. 敏感資訊過濾：絕不記錄 `api_key`、token、或使用者語音轉寫內文（僅記錄長度或 hash）。
- **驗證方式：**
  - 執行 `--dry-run --text "demo"`，以 regex 驗證每行日誌包含 ISO8601 timestamp、level、logger name。
  - 以 `grep -i "FAKE_VALUE_FOR_TEST"` 確認無假憑證外洩到日誌（測試用）。
- **優先級：** P2

### ENTRY-7：自動續 turn 無上限，可能無限循環

- **位置：** `scripts/voice_session.py` → `pending_calls` 邏輯與 `response.done` 分支
- **現狀：**
  ```python
  elif et == "response.done":
      if pending_calls:
          await ws.send(json.dumps({"type": "response.create"}))
          pending_calls.clear()
  ```
  只要模型持續回傳 function call，就會不斷 `response.create()`。
- **影響：**
  - 模型異常或工具回傳觸發新 function call 時，可能形成無限迴圈，持續消耗 API 額度與本機資源。
  - 無人工介入出口（除了 Ctrl-C）。
- **建議修法：**
  1. 引入 `max_turns`（預設 10）與 `turn_count`：
     ```python
     turn_count = 0
     ...
     elif et == "response.done":
         turn_count += 1
         if pending_calls and turn_count < max_turns:
             await ws.send(json.dumps({"type": "response.create"}))
             pending_calls.clear()
         elif turn_count >= max_turns:
             print("turn limit reached; ending session", file=sys.stderr)
             break
     ```
  2. 達到上限時可選送出 `response.cancel` 再結束。
- **驗證方式：**
  - mock server：持續回傳 `response.function_call_arguments.done` 與 `response.done`。驗證腳本在 `max_turns` 後主動結束，且送了預期次數的 `response.create`。
- **優先級：** P2

### ENTRY-8：`observe-demo.sh` 預設寫入 repo 外固定路徑且無清理保證

- **位置：** `scripts/observe-demo.sh` → `OUT="${1:-/tmp/dh-observe}"`
- **現狀：** 未傳參數時寫入 `/tmp/dh-observe`；`rm -f "$OUT"/*.png` 只清除舊有 PNG；腳本無 `trap` 確保異常退出時清理子行程。
- **影響：**
  - 與測試規範「不讀寫 repo 外路徑」（`/tmp` 測試沙箱除外）不一致；此腳本非測試，預設路徑仍可能殘留檔案。
  - 若 `desktop-harness` 或 `screencapture` 子行程異常，背景截圖迴圈可能殘留。
- **建議修法：**
  1. 改用 `mktemp -d`：
     ```bash
     OUT="${1:-$(mktemp -d "/tmp/dh-observe.XXXXXX")}"
     trap 'rm -rf "$OUT"; kill $CAP 2>/dev/null || true' EXIT
     ```
  2. 若需保留帧供事後查看，改為要求明確傳入輸出路徑，並在文件註明「呼叫端負責清理」。
  3. `wait "$CAP"` 已有，但補上 `|| true` 與 trap 更穩健。
- **驗證方式：**
  - `bash -x scripts/observe-demo.sh` 執行後，檢查 `/tmp` 無殘留 `dh-observe*` 目錄（trap 生效）。
  - 模擬 `desktop-harness` 立即失敗（如 `PATH` 設為空），驗證背景 `screencapture` 迴圈被終止。
- **優先級：** P2

---

## 與現有 findings 的關係

| 新發現 | 對應既有 finding | 說明 |
|--------|------------------|------|
| ENTRY-1 | TR-1 | 既有 findings 已指出 WS 無逾時；此處給出具體程式碼位置與 patch 級建議 |
| ENTRY-2 | TR-2 | 既有 findings 已指出阻塞問題；此處補上 AppKit main-thread 相容性決策點 |
| ENTRY-3 | TR-1 | 補上退避演算法與可重試／不可重試錯誤分類 |
| ENTRY-7 | TR-3 | 補上 `max_turns` 具體實作骨架 |
| ENTRY-4, ENTRY-5 | TR-5 | 對應 `helpers`／固定 sleeps 議題，落到 `demo.py` 具體位置 |
| ENTRY-6 | OBS-3 | 對應 voice session 可觀測性，補上結構化日誌 schema |
| ENTRY-8 | PERC-3 | 對應截圖／暫存檔清理，落到 `observe-demo.sh` 具體位置 |

---

## 待確認（本次審查未見到原始碼）

- `src/desktop_harness/run.py`：CLI 進入點如何決定 daemon 路由、`_want_daemon()` 邏輯、stdin 讀取是否有大小上限。
- `src/desktop_harness/helpers.py`：`wait` / `wait_stable` / `verify` 實作、`click_text` 重試策略。
- `src/desktop_harness/ax.py`：AX tree walk 的深度限制、`find` 的評分細節。
- `src/desktop_harness/input.py`：`type_text` 逐字延遲、`move_to` 動畫實作。
- `src/desktop_harness/presence.py`：`keep_alive()` 分片長度、overlay 視窗層級。

上述檔案的相關推論請一併參閱既有 `findings-daemon.md`、`findings-perception.md`、`findings-timeouts-recovery.md`。
