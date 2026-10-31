# desktop-harness 效能與可靠性審查報告（fmb-perf）

- **日期：** 2026-08（效能與可靠性專項審查）
- **範圍：** 效能瓶頸、資源洩漏、併發／競態、逾時與重試、錯誤恢復、日誌可觀測性
- **性質：** 本目錄僅為審查報告與建議，**未修改任何原始碼**。所有建議修法均為提案，需另行開分支實作。
- **repo：** YourheroBOB/desktop-harness @ v0.4.2

---

## 範圍與限制（先講清楚）

本次審查基於工作樹提供的檔案內容，**以下檔案未在本次審查視野內**，相關推論標記為「待確認」：

- `src/desktop_harness/helpers.py`（`click_text`、`media_transport`、`wait_stable` 等實作）
- `src/desktop_harness/ax.py`（AX tree walk 實作）
- `src/desktop_harness/input.py`（HID click/type 實作）
- `src/desktop_harness/run.py`（CLI 進入點、daemon 路由）
- `src/desktop_harness/presence.py`（overlay 實作）

這些檔案的行為引用 `docs/PRE-RELEASE-REVIEW.md` 的既有發現（#9、#10、#13 等）作為交叉參考，不重複展開，只標記「與本次發現相關、需一併處理」。

已完整審查：`daemon.py`、`windows.py`、`capture.py`、`safety.py`、`admin.py`、`selftest.py`、`demo.py`、`voice_tools.py`、`scripts/voice_session.py`、`scripts/observe-demo.sh`、`install.sh` 及主要文件。

---

## 優先級定義

| 級別 | 定義 |
|------|------|
| **P0** | 會讓主要功能整體失效、掛死、或單一事件可讓 daemon 崩潰 — 應優先修 |
| **P1** | 明顯的效能損失、資源洩漏、或可靠性缺口 — 排入近期迭代 |
| **P2** | 打磨項：可觀測性、邊界情況、測試隔離 — 有空就做 |

---

## 發現總表

| ID | 領域 | 標題 | 優先級 | 詳細 |
|----|------|------|--------|------|
| DAEMON-1 | 併發 | 單執行緒 accept 迴圈 + 無連線逾時 → 一個掛住的 client 讓整個 daemon 無回應 | **P0** | [findings-daemon.md](./findings-daemon.md) |
| DAEMON-2 | 錯誤恢復 | 連線處理中未捕捉的 socket 例外會終結整個 daemon | **P0** | [findings-daemon.md](./findings-daemon.md) |
| DAEMON-3 | 逾時 | `exec` 無伺服器端逾時，client 超時後 daemon 仍被佔死 | P1 | [findings-daemon.md](./findings-daemon.md) |
| DAEMON-4 | 效能 | `is_running()` 0.4s ping：daemon 掛掉時每次 CLI 呼叫都多付 400ms | P1 | [findings-daemon.md](./findings-daemon.md) |
| DAEMON-5 | 競態 | `daemon start` 單例檢查為 TOCTOU，兩個並發 start 可產生雙实例 | P2 | [findings-daemon.md](./findings-daemon.md) |
| DAEMON-6 | 競態 | SIGTERM 不會執行 `finally` 清理，留下 stale socket/pid | P2 | [findings-daemon.md](./findings-daemon.md) |
| DAEMON-7 | 穩健性 | 請求 buffer 無大小上限；token 比較非 constant-time | P2 | [findings-daemon.md](./findings-daemon.md) |
| PERC-1 | 效能 | `find_app` 每次做完整 NSWorkspace 列舉；`activate` 輪詢每 80ms 一次全列舉 | P1 | [findings-perception.md](./findings-perception.md) |
| PERC-2 | 效能 | `capture.screenshot` 每次呼叫重新全量列舉視窗 + 子字串 first-hit 匹配 | P1 | [findings-perception.md](./findings-perception.md) |
| PERC-3 | 資源洩漏 | `TMP` 截圖檔永不清理 — 長跑 daemon / observe loop 無限累積 PNG | **P1** | [findings-perception.md](./findings-perception.md) |
| PERC-4 | 競態 | doctor 寫固定路徑 `dh-doctor.png`，併發執行互相覆蓋 | P2 | [findings-perception.md](./findings-perception.md) |
| PERC-5 | 效能 | `activate` 焦點確認採忙等輪詢 + 重複 `activateWithOptions_`（與 agent host 焦點戰爭） | P2 | [findings-perception.md](./findings-perception.md) |
| TR-1 | 逾時 | `voice_session.py`：WS 連線無 `open_timeout`、事件迴圈無 idle timeout、無重試退避 | P1 | [findings-timeouts-recovery.md](./findings-timeouts-recovery.md) |
| TR-2 | 併發 | voice tool `execute()` 同步阻塞在 asyncio 事件迴圈，長動作卡死音訊串流 | P1 | [findings-timeouts-recovery.md](./findings-timeouts-recovery.md) |
| TR-3 | 重試 | `response.done` + `pending_calls` 自動續 turn 無上限，可能無限循環 | P2 | [findings-timeouts-recovery.md](./findings-timeouts-recovery.md) |
| TR-4 | 錯誤恢復 | `safety.audit()` 靜默吞掉所有例外；audit log 無輪替 | P1 | [findings-timeouts-recovery.md](./findings-timeouts-recovery.md) |
| TR-5 | 待確認 | `helpers`／`input` 固定 sleeps（引用 PRE-RELEASE-REVIEW #13，未重複展開） | P2 | [findings-timeouts-recovery.md](./findings-timeouts-recovery.md) |
| TR-6 | 測試隔離 | `selftest` daemon roundtrip 會停掉使用者已在跑的 daemon，改變全域狀態 | P2 | [findings-timeouts-recovery.md](./findings-timeouts-recovery.md) |
| OBS-1 | 可觀測性 | daemon 零請求日誌：無 op／耗時／成功失敗計數 | P1 | [findings-observability.md](./findings-observability.md) |
| OBS-2 | 可觀測性 | audit log 覆蓋不完整且無保留政策（引用 PRE-RELEASE-REVIEW #18） | P2 | [findings-observability.md](./findings-observability.md) |
| OBS-3 | 可觀測性 | voice session 事件只 `print`，無結構化輸出與錯誤分類 | P2 | [findings-observability.md](./findings-observability.md) |
| OBS-4 | 可觀測性 | selftest 已印每項耗時（好）— 建議加上 daemon 路徑 vs in-process 的對照數字 | P2 | [findings-observability.md](./findings-observability.md) |

---

## 檔案索引

| 檔案 | 內容 |
|------|------|
| [findings-daemon.md](./findings-daemon.md) | daemon 併發、競態、逾時、錯誤恢復 |
| [findings-perception.md](./findings-perception.md) | windows / capture 效能與資源洩漏 |
| [findings-timeouts-recovery.md](./findings-timeouts-recovery.md) | 逾時、重試、錯誤恢復（含 voice_session、audit、selftest） |
| [findings-observability.md](./findings-observability.md) | 日誌與可觀測性 |
| [verification-plan.md](./verification-plan.md) | 不觸碰正式服務、不寫 repo 外路徑的驗證方案 |

## 驗證原則（所有 finding 共通）

1. **不連線任何網路正式服務**：voice 驗證一律 `--dry-run` 或 mock WebSocket；daemon 驗證一律用 `DH_SOCKET`／`DH_TOKEN_PATH` 指到 `tmp_path`。
2. **不讀寫 repo 外路徑**（`/tmp` 測試沙箱除外，使用 `tempfile`／`tmp_path`）。
3. **不改使用者目前正在跑的 daemon**：測試前記錄 `daemon status`，測試後還原。
4. 假憑證一律使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串，絕不使用真實格式前綴。
