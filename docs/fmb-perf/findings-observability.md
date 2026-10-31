# Findings — 日誌與可觀測性

---

## OBS-1（P1）daemon 零請求日誌：無 op、耗時、成功失敗計數

**位置：** `daemon.py` — `serve()` 啟動後只印兩行（listening + token 路徑），之後**完全靜默**。每個 exec 的成敗、耗時、例外都只回給單一 client，不留任何伺服器側痕跡。

**影響：**
- **排障極限低**：DAEMON-1/2/3 修好後，若再發生「agent 報 daemon 卡／慢／死」，事後無任何證據可查（何時開始卡？最後一個請求是什麼？exec 平均多久？）。audit log 只記 helper 層事件，不含 daemon 協議層。
- 「agent 步驟變慢」的量測目前只能靠 client 端間歇抽樣（selftest 印 ms），無法回答「是 daemon 變慢還是系統變慢」。
- 對一個設計上就要長跑的背景服務，這是可靠性工程的基本缺口。

**建議修法：**
1. 每個請求一行結構化日誌（JSONL，與 audit 同風格）到 `~/.desktop-harness/daemon.log`（可 `DH_DAEMON_LOG` 覆寫；`0600`；沿用 TR-4 的輪替機制）：
   ```json
   {"ts": ..., "op": "exec", "ok": true, "ms": 412, "code_bytes": 180, "err": ""}
   ```
   `exec` 的 `code_bytes` 記長度**而非內容**（腳本可能含敏感字串，不落日志）。
2. 新增 `op: "stats"`：回傳起動時間、累計請求數、失敗數、最後 20 筆耗時 —— `desktop-harness daemon status` 直接顯示，讓使用者/agent 一眼判斷健康度。
3. 例外路徑（DAEMON-2 的 catch）也記一行 `{"op":"conn_error","err":...}`。

**驗證方式：** 沙箱 daemon（`DH_SOCKET`／`DH_TOKEN_PATH`／`DH_DAEMON_LOG` 全指到 `tmp_path`）：跑 5 個 ping + 1 個 exec + 1 個壞 JSON → 斷言 log 恰 7 行、欄位齊全、exec 的 `ms` > 0、壞 JSON 有 `ok:false` 記錄；`stats` op 回傳的計數與 log 行數一致。

**優先級：** P1（與 DAEMON-2 同 PR 實作最順 —— 反正要在 catch 裡加輸出）

---

## OBS-2（P2）audit log 覆蓋不完整、無保留政策、無 redaction 說明

**位置：** `safety.audit()` — 目前呼叫點（依可見程式碼）：`activate`／`activate_skip`（windows.py）、`screenshot`（capture.py）。`type_text`／`click_text`／`set_field`／`hotkey` 等其他 mutation 未見呼叫（`helpers.py`／`input.py` 未審，待確認；PRE-RELEASE-REVIEW #1 已指出同樣缺口）。

**影響：** 稽核軌跡有洞 —— 事后無法回答「agent 昨天到底點了/打了什麼」。輪替與靜默失敗問題已在 TR-4 處理，此處聚焦**覆蓋與內容政策**。

**建議修法：**
1. 覆蓋：所有 mutation helper 統一在單一 gate 函式內 audit（與 sensitive-app gate 同一個 choke point，一次補齊兩件事）。`click_text` 記目標 label；`type_text` **只記長度不記內容**（內容可能含密碼/個資 —— 現行「set_field 不記值」的直覺是對的，成文化為政策）。
2. 文件：在 SECURITY.md 補一節「audit log 記什麼／不記什麼／保留多久」，讓使用者知道軌跡邊界。
3. 時間戳建議同時記 ISO 8601 字串（目前只有 epoch float，人讀困難）。

**驗證方式：** 補齊後，跑一輪 demo（沙箱 `DH_AUDIT_LOG`），斷言 audit 涵蓋：activate、click、type_text（長度）、screenshot 各至少一筆；grep 不得出現 type_text 的實際內容。

**優先級：** P2（覆蓋補齊部分若 helpers 審後確認全缺，可升 P1）

---

## OBS-3（P2）voice session 事件只 `print`，無錯誤分類與結構化輸出

**位置：** `scripts/voice_session.py` — `print("ERROR:", event)`、tool 呼叫/結果皆純 print。

**影響：** voice 路徑掛掉時只有一坨終端輸出，無法事後分析（哪類錯誤？tool 呼叫了幾次？每次多久？）。experimental 階段可接受，但要升級成 hotkey 常駐產品（VOICE.md 規劃）就不夠。

**建議修法：** 最小改動 —— 每個 tool 呼叫記 `{tool, ms, ok}` 一行 JSONL 到 `~/.desktop-harness/voice.log`（模式同 OBS-1）；錯誤事件依 `event["error"]["type"]` 分類計數。保持 stderr 給人類、JSONL 給機器的分離。

**驗證方式：** `--dry-run --text` + fake execute（不連網）跑一輪 → 斷言 voice.log 有對應行；錯誤分類用假 server 餵 error 事件驗證（同 TR-1 的本機假 server 法）。

**優先級：** P2

---

## OBS-4（P2）selftest 已印每項耗時（好）— 補 daemon vs in-process 對照

**位置：** `selftest.py` — `check()` 已印 `(ms)`，這是現有的好設計。

**建議修法（增強）：** 加一個 `daemon path vs in-process` 的對照項：同一個 `labels()` 呼叫各跑一次（沙箱 daemon，同 TR-6 的隔離方式），印出兩個 ms —— 這正是 README 賣點「daemon 讓第二步變快」的**持續性回歸指標**，效能退化（例如 PERC-1 未修、DAEMON-4 退化）會直接在 selftest 上現形。

**驗證方式：** 跑 selftest，斷言對照項兩個數字都印出、且 daemon 路徑含啟動成本時仍合理（誤差不影響 PASS/FAIL，僅供人類閱讀 —— 保守不把它做成硬斷言，避免 flaky）。

**優先級：** P2
