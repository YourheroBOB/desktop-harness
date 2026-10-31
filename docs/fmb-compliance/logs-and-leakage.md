# 記錄檔與輸出可能外洩欄位盤點

> 盤點所有「會留下文字或影像紀錄」的輸出面，評估欄位級的外洩風險。座標均為虛構示意。

## 1. `~/.desktop-harness/audit.jsonl`（audit log）

由 `safety.audit(event, detail)` 寫入，格式：`{"ts": <epoch>, "event": <str>, "detail": {...}}`。

| 已確認欄位（來源：`capture.py`） | 值 | 風險 |
|------------------------------------|-----|------|
| `ts` | epoch 時間 | 低（行為時間側寫） |
| `event` | `"screenshot"` 等 | 低 |
| `detail.app` | 呼叫者指定的 app 名 | 中（app 名本身可透露活動，如特定銀行/醫療 app） |
| `detail.window_id` | 視窗 id | 低 |
| `detail.path` | 截圖完整路徑 | 低 |

| 待確認欄位（呼叫端為 `helpers.py`，未在視野；依 review #18、ADR-0008 描述） | 推測值 | 風險 |
|----------------------------------------------------------------------------|---------|------|
| `click_text` 的目標文字 | **UI 標籤文字**——若 agent 以文件內容/訊息對象名稱做 click_text（例：點擊郵件清單中的收件人名），該文字即個資，**原樣入 log** | **高（待確認）** |
| `activate`/`open_app` 的 app 名 | app 名 | 中 |
| `set_field` | ADR-0008 明言**刻意不記值**（避免密碼入 log）——良好設計，應保持 | 低 |

**`safety.audit` 的例外吞噬問題（TR-4）**：寫檔失敗時 `except Exception: pass`——審計紀錄靜默失敗。合規上審計是安全維護計畫的必要措施，靜默失敗等於無審計，應改為 stderr 警告（已在 fmb-perf 建議中）。

## 2. daemon（`daemon.py`）

- **現況零請求日誌**（OBS-1）——反向問題：審計面反而是「什麼都沒記」。對合規（可歸責性）而言，daemon 作為「本機特權 exec 端點」至少應記錄 op、時間、結果碼（**不記 code 內容**，避免腳本內含個資入 log）。
- 通訊為 NDJSON over Unix socket（0600 + token），攔截面限同 UID——本機風險受 ADR-0004 界定，可接受。

## 3. stdout／stderr（回傳 agent）

- agent 腳本可 `print()` 任何讀到的 AX 值／labels／截圖路徑——**這是最大且最無約束的外洩面**：內容直接進 agent host／LLM context（跨境）。程式層無法也不應逐一過濾（exec 模型使然），只能靠：
  1. skill 政策（現有 SKILL.md 僅規範 consent，**未規範「不要把螢幕個資原樣回傳／印出」**——建議補一條最小化政策）；
  2. 業務層告知（見 COMP-1）。
- `voice_session.py` 直接 `print(delta)` 語音 transcript、`print("ERROR:", event)` 整包事件 JSON（可能含內容欄位）——若 session 紀錄被 shell history/終端 buffer 保留，個資留痕於本機 terminal；建議 transcript 預設不印或加遮罩開關。

## 4. 其他落痕位置

| 位置 | 內容 | 風險 |
|------|------|------|
| `dh-doctor.png`（`$TMPDIR` 固定檔名） | 全螢幕/視窗截圖 | 中（PERC-4 併發覆蓋＋無清理；截圖本身見 D1） |
| `scripts/observe-demo.sh` 輸出 `/tmp/dh-observe/` | 24+ 張全螢幕連續影格 | **高**（連續全螢幕錄影等價物；開頭僅清同目錄舊檔，檔案本身留到使用者手動刪） |
| shell history / 終端 buffer | heredoc 腳本內容（agent 可能寫入當事人姓名查詢、訊息內容做為參數） | 中（本機側，建議業務 SOP 使用免寫入 history 的方式） |
| `.gitignore` | 已排除 `*.png`——截圖不會入 git ✅；但 `~/.desktop-harness/` 不在 repo 內，本來就不會入 git | — |
| GitHub（`check-update`、push） | 僅版本比對／程式碼；review #23 確認無 secret 入庫 ✅ | 低 |

## 5. 欄位級建議（優先順序）

1. **確認並遮罩 `click_text` audit 的目標文字**（若確實記錄）：改成長度或 hash，或僅記 role＋座標近似值——保持「可審計但不留個資」。（高）
2. `safety.audit` 失敗改為可見警告（TR-4 既有建議，合規加權）。（高）
3. `voice_session.py` transcript 印出加 `--quiet-transcript` 或預設遮罩。（中）
4. daemon 增加最小請求日誌（op/時間/結果碼，不含 code）。（中，OBS-1 既有）
5. SKILL.md 增補「輸出最小化」政策：不要把 AX 值／截圖內容原樣回傳或寫入 repo 文件。（中，屬政策層）
