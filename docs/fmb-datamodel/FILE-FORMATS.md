# desktop-harness 檔案與 wire format

> 本文件描述 repo 內格式及執行期 artifact。路徑中的 home、cache 與 temp 僅表示用途；本文件不附實際檔案內容、token 或 screenshot。

## 1. Repo 檔案格式

| 檔案／類型 | 格式 | 主要用途 | 結構重點 |
|---|---|---|---|
| `pyproject.toml` | TOML | Python package metadata、build config、wheel package data | `project`、`project.scripts`、`build-system`、`tool.hatch.build` |
| `src/**/*.py` | Python | CLI、helpers、daemon、safety、voice executor | import-time module globals 與 runtime dict／list |
| `scripts/*.sh` | POSIX shell／Bash | 安裝、observe capture loop | 環境變數、路徑與 subprocess |
| `scripts/voice_session.py` | Python | 實驗性語音 WebSocket session | JSON message |
| `SKILL.md` | Markdown + YAML front matter | agent skill | front matter 有 `name`、`description` |
| `docs/**/*.md` | Markdown | 使用、安全、架構與資料模型 | Mermaid fenced block |
| `desktop-harness` | POSIX shell launcher | 從 working tree 執行 module | `PYTHONPATH` 與 Python interpreter 選擇 |
| `agent-workspace/agent_helpers.py` | Python | 使用者自訂 helper 擴充點 | dynamic、不可預先枚舉 |

### 1.1 `pyproject.toml`

已確認的 top-level schema：**[S]**

```text
[project]
  name: str
  version: str
  description: str
  requires-python: str
  dependencies: str[]

[project.scripts]
  desktop-harness = "desktop_harness.run:main"

[build-system]
  requires: str[]
  build-backend = str

[tool.hatch.build.targets.wheel]
  packages = str[]

[tool.hatch.build.targets.wheel.force-include]
  "<source>" = "<package-destination>"
```

Wheel 會把頂層 `SKILL.md` force-include 為 package data；`skill` command 的安裝／套件行為因此不以 repo checkout 為唯一前置條件。

### 1.2 `SKILL.md`

檔案開頭是 YAML front matter：**[S]**

```yaml
name: desktop-harness
description: >
  Multi-line description.
```

`description` 使用 YAML folded scalar `>`。其後是 Markdown。Front matter 不是 JSON，也沒有獨立的 machine schema。

### 1.3 文字型 CLI 輸出

| 介面 | 格式特徵 |
|---|---|
| doctor | 每個檢查一行，狀態為 `PASS` 或 `FAIL`，可附 detail。 |
| selftest | 每個測試一行，狀態為 `PASS` 或 `FAIL`，可附 elapsed time 與 exception 類型。 |
| demo | 步驟式敘述，數值以 Python representation 輸出。 |
| skill | 原樣輸出 Markdown。 |
| daemon status | 狀態文字；exact layout 尚未驗證。 |

這些格式主要供人閱讀，不應以固定欄位解析；需要 machine-readable 結果時應另增明確 JSON contract，而不是解析本文件描述的文字。

## 2. 執行期 artifact

| Artifact | 預設位置／產生方式 | 格式 | 權限／生命週期 |
|---|---|---|---|
| Audit log | `~/.desktop-harness/audit.jsonl`，可由環境變數覆寫 | JSON Lines | append-only；目前無 rotation |
| Daemon socket | `~/Library/Caches/desktop-harness/daemon.sock`，可覆寫 | Unix domain socket；內容為 NDJSON | bind 後明確 `0600` |
| Daemon PID | socket path 換成 `.pid` suffix | 單行十進位整數文字 | `0600`；daemon 結束時刪除 |
| Daemon token | `~/.desktop-harness/daemon.token`，可覆寫 | opaque 單行 secret text | `0600`；daemon 結束時目前不刪除 |
| Default screenshot | system temp 下的 `desktop-harness/capture-<pid>-<ns>.png` | PNG binary | 呼叫端管理；無 metadata sidecar |
| Doctor screenshot | system temp 下固定名稱 | PNG binary | doctor 測試產生 |
| Observe frames | caller 指定目錄，observe script 使用 `/tmp/dh-observe` | PNG binary | script 每次先移除舊 frames |
| Installed Grok skill | `~/.grok/skills/desktop-harness/SKILL.md` | Markdown | installer 產生 |
| Agent workspace | repo 內 `agent-workspace/agent_helpers.py`；載入路徑細節待 `helpers.py` 驗證 | Python source | 每個 script namespace 使用 |

### 2.1 路徑解析規則

- `DH_SOCKET` 在 module import 時決定 daemon socket 根路徑。
- PID path 是 socket path 的 `.pid` sibling。
- `DH_TOKEN_PATH` 在 module import 時決定 token path。
- `DH_AUDIT_LOG` 在 module import 時決定 audit path。
- screenshot 預設 temp directory 在 `capture.py` import 時建立。
- 明確指定的 screenshot path 不會被轉成絕對路徑；parent directory 也由 caller 負責準備。

### 2.2 權限語意

| Artifact | 已實作權限 |
|---|---|
| Daemon socket | `0600` |
| Daemon token | `0600` |
| Daemon PID | `0600` |
| Audit log | 由 OS default／umask 決定，source 未明確 chmod |
| Screenshot directory／file | 由 OS default／umask 決定，source 未明確 chmod |

## 3. 環境變數

| 變數 | 型別／解析 | 效果 |
|---|---|---|
| `DH_NO_DAEMON` | presence flag | 強制本機執行，不使用 warm daemon。 |
| `DH_MOUSE_INSTANT` | presence flag | 關閉 mouse movement animation。 |
| `DH_PRESENCE` | presence flag | 啟用／停用 presence UI；預設啟用。 |
| `DH_SAFE` | `1/true/yes` 為 true；`0/false/no` 為 false | safe-mode policy flag。 |
| `DH_ALLOW_SENSITIVE` | `1/true/yes` 為 true | 略過 sensitive-app gate。 |
| `DH_AUDIT_LOG` | path | 覆寫 audit log path。 |
| `DH_SOCKET` | path | 覆寫 daemon socket path。 |
| `DH_TOKEN_PATH` | path | 覆寫 daemon token path。 |
| `GROK_VOICE_MODEL` | model id string | 覆寫實驗性語音 model id。 |

語音 credential 由 process environment 提供；本文件不記錄變數值、格式或任何 credential。

## 4. Daemon NDJSON protocol

### 4.1 Framing

Protocol 是 newline-delimited JSON over Unix stream socket。**[S]**

```text
frame   = JSON-object LF
client  = request-frame
server  = response-frame
```

特性：

- client 以 JSON object 加換行送出一個 request。
- server 讀到第一個 newline 為止。
- server 回傳一個 response frame 後結束該 connection。
- 使用 Python JSON defaults；非 ASCII content 預設以 JSON escape 表示。
- source 沒有明確限制單一 frame 大小。
- server accept loop 為循序處理；listen backlog 為 8。
- client default socket timeout 為 60 秒。
- daemon server 本身沒有 execution timeout。

### 4.2 Request schema

Canonical allowed operations：

| `op` | 額外欄位 | 結果 |
|---|---|---|
| `ping` | 無 | health response |
| `quit` | 無 | 終止 daemon |
| `exec` | `code: str` | 在常駐 namespace 執行 source |

每個 request 都必須帶與 daemon 保存值相同的 opaque token。client 若能讀到 token file，會自動加入 request。

### 4.3 Response schema

| Response | 結構 |
|---|---|
| Ping | `{"ok": true, "pong": true}` |
| Quit | `{"ok": true}` |
| Exec | `{"ok": bool, "stdout": str, "stderr": str}` |
| Parse/auth/unknown-op error | `{"ok": false, "error": str}` |

Exec source 的 exception 會被轉成 traceback text，置於 `stderr`，且 `ok` 為 false。

## 5. Audit JSON Lines

### 5.1 每行 schema

```text
audit-file = audit-row LF audit-row LF ...
audit-row  = {
  "ts": <number>,
  "event": <string>,
  "detail": <object>
}
```

特性：

- 檔案不是 JSON array，而是每行獨立 JSON object。
- 每列由 `json.dumps(..., default=str)` 產生。
- append mode；不重寫既有列。
- `ts` 是 Unix epoch 秒數。
- `detail` 預設為空 object。
- 寫入失敗被吞掉，不會阻止 helper operation。
- 沒有 rotation、retention、size limit 或刪除 API。

完整 JSON Schema 見 [`JSON-SCHEMAS.md`](./JSON-SCHEMAS.md)。

## 6. Screenshot PNG

- 影像來源是 CoreGraphics window list。
- 編碼器為 `NSBitmapImageRep`，PNG file type。
- 預設 scope 為單一 window；無 target 時可擷取主 display。
- PNG 檔沒有本專案自訂的 sidecar metadata schema。
- explicit `path` 可覆寫輸出位置。
- 預設檔名格式：

```text
capture-<process-id>-<nanosecond-timestamp>.png
```

## 7. Voice WebSocket JSON

語音路徑是實驗性 scaffold，使用 WebSocket text message 傳送 JSON object。**[S]**

### 7.1 Client → server

| Message | 結構重點 |
|---|---|
| Session update | `type=session.update`；包含 voice、instructions、tools、turn detection。 |
| Text conversation item | `type=conversation.item.create`；item type 為 message，role 為 user，content 為 input-text array。 |
| Response request | `type=response.create`。 |
| Function output | `type=conversation.item.create`；item type 為 function call output，含 call id 與 tool result。 |

### 7.2 Server → client

| Event type | 本專案使用的欄位 |
|---|---|
| `error` | 任意 error object；程式以文字輸出。 |
| `session.updated` | session acknowledgement。 |
| `response.done` | response completion marker。 |
| `response.function_call_arguments.done` | `name`、`call_id`、`arguments`。 |
| `response.output_audio_transcript.delta` | `delta`。 |
| `response.output_text.delta` | `delta`。 |
| `conversation.item.input_audio_transcription.completed` | transcription completion marker。 |

`arguments` 在 executor 可接受 JSON object 或 JSON string；無效 JSON string 會轉為 error envelope。

### 7.3 Dry-run 語意

- `voice_tools.execute(..., dry_run=True)` 不呼叫 helper，只回傳 dry-run envelope。
- `scripts/voice_session.py --dry-run` 在沒有 credential 的 local demo branch 會執行部分 read-only helper；因此它不等同於「完全不碰本機」。本文件不記錄其輸出內容。

## 8. Daemon metadata formats

### 8.1 PID file

```text
pid-file = decimal-integer [LF]
```

用途是 single-instance hint 與 process liveness check。它不是 authoritative lock。

### 8.2 Token file

```text
token-file = opaque-secret-text [LF]
```

- 由 secure random source 產生。
- 檔案權限為 `0600`。
- 內容刻意不記錄，也不應進 audit、文件或版本控制。
- daemon quit 目前只移除 socket 與 PID，不移除 token。

### 8.3 Socket

Socket 本身不是可移植檔案格式；其可觀察 contract 是 Unix stream socket + NDJSON frame。

## 9. 資料庫與資料表

### 9.1 現況

目前沒有：

- SQLite、SQLAlchemy、Django ORM 或其他 database engine；
- table／column declaration；
- primary key／foreign key declaration；
- migration 或 seed；
- database dependency。

因此本專案沒有可列出的資料庫表。`list_apps()`、`list_windows()` 等 collection 是 runtime query result，不是資料表；audit JSONL 是 append-only log，不是 relational table。

### 9.2 若未來新增資料庫

至少應補齊：

1. entity 與 table mapping；
2. column type、nullability、default；
3. primary／foreign key 與 index；
4. migration version；
5. data retention 與 deletion；
6. encryption 與 backup policy；
7. runtime location 與權限。

## 10. 保留與清理矩陣

| Artifact | 自動清理 | 已知限制 |
|---|---|---|
| Audit log | 否 | 無 rotation／retention。 |
| Default screenshot | 否 | 呼叫端或 OS temp cleanup 處理。 |
| Doctor screenshot | 否 | 固定 temp path。 |
| Observe frames | 是 | observe script 啟動時移除舊 PNG。 |
| Daemon socket | 是 | daemon 正常結束時刪除。 |
| Daemon PID | 是 | daemon 正常結束時刪除。 |
| Daemon token | 否 | daemon 結束後仍保留。 |
| Installed skill | 否 | installer 覆寫時更新。 |
