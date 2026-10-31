# 事件模型與關鍵事件目錄

> 本章定義「一行一事件」的 JSONL schema、事件目錄、欄位命名規範、保留策略。
> 對應落地檔：`~/.desktop-harness/events.jsonl`（提案，env `DH_EVENTS_LOG`；總開關 `DH_OBSERVABILITY=0`）。

## 1. 事件封包（envelope）

```json
{
  "schema_version": 1,
  "ts_ms": 1754899200123,
  "mono_ms": 8312,
  "level": "info",
  "event": "click_text",
  "session_id": "dh-1234-1754899199000",
  "pid": 1234,
  "route": "daemon",
  "fields": { }
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `schema_version` | int | 事件 schema 版本，破壞性變更時 +1 |
| `ts_ms` | int | epoch 毫秒（wall clock，用於跨程序對齊） |
| `mono_ms` | int | monotonic 毫秒（用於耗時，不受改系統時鐘影響；彌補 G8） |
| `level` | str | `debug` / `info` / `warn` / `error` |
| `event` | str | 事件名（見目錄），snake_case |
| `session_id` | str | `dh-<pid>-<啟動 epoch_ms>`；**不含使用者名稱或隨機 secret** |
| `pid` | int | 本機進程 id（internal） |
| `route` | str | `inprocess` / `daemon` / `voice`（實驗性） |
| `fields` | object | 事件專屬欄位，見下表；**只允許 allowlist 欄位** |

## 2. 欄位命名規範

| 規則 | 範例 |
|------|------|
| 耗時一律毫秒整數，後綴 `_ms` | `duration_ms` |
| 大小一律 bytes 整數，後綴 `_bytes` | `screenshot_bytes` |
| 計數後綴 `_count` | `nodes_count` |
| 布林前綴語意化 | `already_frontmost`、`truncated` |
| 敏感原文一律改 `_hash`（SHA-256 hex 前 12 碼）+ `_len` | `label_hash`、`label_len` |
| 列舉值用小寫 snake | `resolved_by=exact\|prefix\|substring\|bundle\|open_a` |
| 不允許自由文字（free text）欄位，除 `sanitized_message`（正規化後） | — |

## 3. 敏感級別（與 `SENSITIVE-FIELDS.md` 連動）

| 級別 | 意義 |
|------|------|
| `internal` | 可入 events.jsonl（本機檔案，權限 0600，見告警 ALRT-06） |
| `restricted` | 預設只記 hash/len，或由開關決定 |
| `forbidden` | **永不入欄**；寫入即視為資安事件（ALRT-06） |

## 4. 事件目錄

### 4.1 工作階段（session）

| 事件 | 觸發時機 | 欄位 | 敏感級 |
|------|----------|------|--------|
| `cli_invoke` | CLI 啟動、腳本開始前 | `mode`(inprocess/daemon)、`argv_count`、`stdin_bytes`、`daemon_probe_ms` | internal（**腳本內容本身永遠不入欄**） |
| `cli_exit` | 程序結束 | `duration_ms`、`exit_code`、`error_class?` | internal |

### 4.2 應用／視窗

| 事件 | 觸發時機 | 欄位 | 敏感級 |
|------|----------|------|--------|
| `app_open` | `open_app` / `activate` | `app`、`bundle_id`、`resolved_by`、`already_frontmost`、`duration_ms`、`result` | app/bundle_id = internal |
| `window_list` | `list_windows`（可選，預設 off） | `windows_count`、`duration_ms` | internal |

### 4.3 感知（AX／截圖）

| 事件 | 觸發時機 | 欄位 | 敏感級 |
|------|----------|------|--------|
| `ax_snapshot` | 每次 AX 走訪 | `app`、`pid`、`interactive_only`、`max_nodes`、`nodes_count`、`truncated`、`walks`、`duration_ms` | internal |
| `ax_find` | `find` / `click_text` 比對 | `app`、`role?`、`query_len`、`query_hash`、`hits_count`、`walks_count`、`duration_ms`、`result` | query 原文 = **restricted → 只記 hash/len** |
| `screenshot` | 視窗／畫面截圖 | `app`、`window_id`、`width`、`height`、`bytes`、`duration_ms`、`path_basename`、`result`、`blocked?` | 影像內容 = forbidden；完整路徑 = restricted（只記 basename） |
| `media_transport` | 讀取播放器狀態 | `app`、`state`、`transport_play`、`row_play`、`duration_ms` | internal（皆布林） |

### 4.4 動作（mutating）

| 事件 | 觸發時機 | 欄位 | 敏感級 |
|------|----------|------|--------|
| `click_text` | 依標籤點擊 | `app`、`role`、`exact`、`label_hash`、`label_len`、`matched_via`(axpress/coords/none)、`duration_ms`、`result`(ok/fallback_xy/miss/blocked/error) | 標籤原文 = restricted |
| `click_xy` | 座標點擊 | `app`、`x`、`y`、`duration_ms`、`result` | 座標 = internal |
| `type_text` | 打字 | `app`、`char_count`、`duration_ms`、`result` | **內容 = forbidden；只記長度** |
| `hotkey` | 快捷鍵 | `app`、`keys`、`result` | internal（快捷鍵組合非內容） |
| `set_field` | 設值 | `app`、`field_label_hash`、`field_label_len`、`value_len`、`result` | **值 = forbidden** |
| `scroll` / `drag` | 捲動／拖曳 | `app`、`duration_ms`、`result` | internal |
| `ensure_media_playing` | 媒體播放決策 | `app`、`action`(none/press_play)、`verify_state`、`result` | internal |

### 4.5 安全（safety）

| 事件 | 觸發時機 | 欄位 | 敏感級 |
|------|----------|------|--------|
| `safety_block` | 任一閘門阻擋 | `gate`(app_allowed/frontmost_allowed/helper_allowed)、`app`、`bundle_id`、`reason` | internal（阻擋紀錄需要知道對象） |
| `safety_override` | `DH_ALLOW_SENSITIVE=1` 生效期間發生阻擋類檢查 | `gate`、`app` | warn 級；每次 override 使用都要留痕 |
| `audit_write_failed` | 任一觀測寫入失敗 | `target`(audit/events/metrics)、`error_class` | **必發**：彌補 G2 靜默失敗 |

### 4.6 daemon

| 事件 | 觸發時機 | 欄位 | 敏感級 |
|------|----------|------|--------|
| `daemon_start` / `daemon_stop` | 生命週期 | `pid`、`socket_path`、`socket_mode`、`token_created`、`duration_ms?` | token 內容 = forbidden；只記「有無建立」 |
| `daemon_request` | 每次 socket 請求 | `op`(ping/exec/quit)、`ok`、`duration_ms`、`code_len`、`error_class?` | exec 腳本內容 = forbidden；只記長度 |
| `daemon_stale_socket` | 連線失敗並清理 | `action`(unlinked/kept)、`detail` | internal |

### 4.7 健康檢查

| 事件 | 觸發時機 | 欄位 | 敏感級 |
|------|----------|------|--------|
| `doctor_check` | `--doctor` 每一項 | `name`、`status`、`detail`（scrub 後，如節點數／位元組數） | detail 走 sanitizer |
| `selftest_step` | selftest 每一步 | `name`、`status`、`duration_ms` | internal |
| `error` | 任何被捕捉並分類的錯誤 | `error_class`、`module`、`func`、`sanitized_message`、`session_id` | 訊息必須正規化（數字→`<n>`、路徑→`<path>`） |

### 4.8 presence（低頻但便宜）

| 事件 | 觸發時機 | 欄位 |
|------|----------|------|
| `presence_toggle` | `enable_agent_cursor` / `hide_agent_presence` | `enabled`、`reason` |

## 5. `error_class` 枚舉（初版）

`permission_denied`（Accessibility／Screen Recording 未授權）、
`safety_blocked`、`app_not_found`、`window_not_found`、
`ax_error`（AX API 失敗／超時）、`ax_empty`（走訪結果空）、
`capture_failed`、`daemon_unreachable`、`daemon_auth_failed`、
`daemon_stale_socket`、`timeout`、`input_failed`、
`io_error`（寫 log／檔案件）、`unknown`。

> 目的：讓 `dh_errors_total{class,module}` 可聚類，而不是一堆獨一無二的 traceback。

## 6. 保留與輪替（提案，對應 ROADMAP #7）

| 檔 | 輪替策略 | 保留 |
|----|----------|------|
| `events.jsonl` | 超過 5MB → `events.jsonl.1`（最多 3 份，舊的刪除） | 最近 3 份 |
| `metrics.jsonl` | 每日彙總为報告後可壓縮保留 30 天 | 30 天 |
| `audit.jsonl` | 同 events（ROADMAP #7 已列） | 依 BOB 決策（見摘要） |

輪替寫入失敗 → 發 `audit_write_failed`，**不得靜默**。

## 7. 寫入路徑要求（落地時的驗收條件）

1. 所有事件只能含 allowlist 欄位；未知欄位在測試環境直接 raise（fail-fast）。
2. 任何內容級字串（`type_text` 值、剪貼簿、AX value）在進入事件前由 redaction 層剝除，不是靠呼叫方自律。
3. `DH_OBSERVABILITY=0` 時不寫 events/metrics，但**安全閘門與 audit 行為不變**（關觀測不等於關安全）。
