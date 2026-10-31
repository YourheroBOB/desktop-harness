# desktop-harness 資料結構

> 對應 `desktop-harness` v0.4.2。欄位型別以 current Python source 為準；標示 **[D]**／**[I]** 的部分表示 source 未完整提供，因此只描述已知的最小契約。

## 1. 一般規則

| 慣例 | 規則 |
|---|---|
| 容器 | 大多數 helper 回傳 `list` 或 `dict`，沒有自訂 ORM entity。 |
| Key 命名 | `snake_case`。 |
| 布林 | Python `bool`。 |
| PID | Python `int`。 |
| 座標 | 以數值表示；目前是全域螢幕 point，而非正規化 0–1 座標。 |
| 空值 | `None` 通常映射為 JSON `null`；部分 macOS 名稱屬性以空字串代替未知值。 |
| 可序列化 | 核心 dict／list 可直接交給 `json.dumps`；audit 使用 `default=str` 作最後備援。 |
| 排序 | App list 會排序；其他 collection 不應依賴順序。 |

## 2. App 與 process

### 2.1 `AppInfo`

來源：`windows.list_apps()`、`windows.frontmost_app()`、`windows.find_app()`。**[S]**

```text
AppInfo = {
  name: str,
  bundle_id: str,
  pid: int,
  active: bool,
  hidden: bool,
}
```

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `name` | `str` | 必有 | macOS localized display name；系統可能回傳空字串。 |
| `bundle_id` | `str` | 必有 | macOS bundle identifier；不保證非空。 |
| `pid` | `int` | 必有 | process identifier。 |
| `active` | `bool` | 必有 | 該 process 是否為 active application。 |
| `hidden` | `bool` | 必有 | 該 process 是否 hidden。 |

`frontmost_app()` 回傳 `AppInfo | None`；`find_app()` 亦回傳 `AppInfo | None`。`list_apps()` 回傳 `list[AppInfo]`，並依「active 優先、name case-insensitive」排序。

### 2.2 App lookup 規則

`find_app(name_or_bundle)` 的解析順序：**[S]**

1. integer：直接視為 PID。
2. exact localized name 或 exact bundle id。
3. name prefix；若多個候選，取最短 name。
4. name／bundle-id substring；若多個候選，取最短 name。
5. macOS bundle-id lookup。

## 3. Window

### 3.1 `WindowInfo`

來源：`windows.list_windows()` 與 `capture.window_info()`。**[S]**

```text
WindowInfo = {
  id: int,
  app: str,
  pid: int,
  title: str,
  x: float,
  y: float,
  w: float,
  h: float,
}
```

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `id` | `int` | 必有 | CoreGraphics window number。 |
| `app` | `str` | 必有 | window owner 的顯示名稱。 |
| `pid` | `int` | 必有 | owner process id。 |
| `title` | `str` | 必有 | window title；macOS 可能不提供而回傳空字串。 |
| `x` | `float` | 必有 | 全域螢幕座標 X。 |
| `y` | `float` | 必有 | 全域螢幕座標 Y。 |
| `w` | `float` | 必有 | 視窗寬度，單位為螢幕 point。 |
| `h` | `float` | 必有 | 視窗高度，單位為螢幕 point。 |

`list_windows()` 只保留：

- window layer 為一般視窗層；
- 寬、高皆至少 50 point；
- 預設只列出 on-screen window。

`window_info(app)` 回傳 `WindowInfo | None`；未指定 app 時取第一個符合條件的 window。**[S]**

## 4. Mouse position

### 4.1 `MousePosition`

最小可驗證契約來自 self-test；`input.py` 未在本次 snapshot 提供。**[T][I]**

```text
MousePosition = {
  x: number,
  y: number,
}
```

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `x` | `float` 或 `int` | 必有 | 全域螢幕 X 座標。 |
| `y` | `float` 或 `int` | 必有 | 全域螢幕 Y 座標。 |

`mouse_pos()` 至少回傳上述兩個 key。`move_to()` 的回傳值在現有文件中被視為 position-like，但 exact shape 未由本次 source 驗證。

## 5. Accessibility 資料

### 5.1 AX node

`ax.py` 與 `helpers.py` 未在本次 snapshot 提供；以下只記錄 architecture contract 明示的最小欄位。**[D][I]**

```text
AxNode = {
  role: str,
  title?: string | null,
  value?: string | number | bool | null,
  frame?: {
    x: number,
    y: number,
    w: number,
    h: number,
  },
  ...additional fields
}
```

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `role` | `str` | 最小契約 | AX role，例如 button、static text 等；實際值由 UI 決定。 |
| `title` | `str` 或 `null` | 選填 | 可見 label／title。 |
| `value` | scalar 或 `null` | 選填 | AX value；runtime 型別可能隨 control 改變。 |
| `frame` | object | 選填 | 螢幕座標 frame；子欄位為 `x`、`y`、`w`、`h`。 |
| 其他欄位 | unknown | 選填 | compact AX snapshot 可能包含額外 metadata。 |

安全與隱私要求：

- 不在文件中列出實際 AX label、title 或 value。
- `frame_on_screen()` 另以獨立 dict／object 判斷 rectangle 是否可用。
- `ax_snapshot()` 的 exact key set、node wrapper 與 required field 仍待 source 補齊。

### 5.2 Label list

`labels()` 回傳 `list[str]`，不是 label object。**[T]**

每個字串是 UI label 的文字表示；內容屬於 runtime UI data，應視為可能敏感，不應持久化到本文件。

### 5.3 Search result

`find()` 與 `click_text()` 都以 AX 搜尋為主，但本次未提供 exact return schema。已確認的限制：

- `click_text()` 優先尋找 AX action。
- 找不到 AX action 時可退回 frame center coordinate click。
- `click_text()` 可接受 exact matching。
- hit object 的完整 key set 為 **[I]／未驗證**，因此不在 JSON Schema 中虛構 required fields。

## 6. Media transport

### 6.1 `MediaTransportState`

來源：`helpers.media_transport()` 的 self-test 與 current media 文件。**[T][D]**

```text
MediaTransportState = {
  state: "playing" | "paused" | "unknown",
  transport_play: bool,
  row_play: bool,
  play: bool,
}
```

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `state` | enum | 必有 | 目前媒體的整體播放狀態。 |
| `transport_play` | `bool` | 必有 | 是否找到 transport-level Play control。 |
| `row_play` | `bool` | 必有 | 是否找到 list/row-level Play control。 |
| `play` | `bool` | 必有 | 為 `transport_play` 的相容 alias，不表示 row play。 |

必須維持的不變量：

```text
state in {"playing", "paused", "unknown"}
play == transport_play
```

`row_play` 不得被誤當成目前 transport 已可播放。

### 6.2 `ensure_media_playing()`

這是 side-effect helper，不是新的持久化 record。其 exact return shape 未由本次 source 提供。已定義的行為是：

1. 先讀取 media state。
2. 已播放時不動作。
3. paused 時只執行一次精確 Play action。
4. action 後重新讀取 state。
5. unknown 時回報 unknown，不反覆嘗試或連按空白鍵。

## 7. Audit data

### 7.1 `AuditRow`

來源：`safety.audit()`。**[S]**

```text
AuditRow = {
  ts: float,
  event: str,
  detail: object,
}
```

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `ts` | `float` | 必有 | Unix epoch timestamp，單位為秒。 |
| `event` | `str` | 必有 | event 名稱；目前為 extensible string。 |
| `detail` | `object` | 必有 | event-dependent detail；空值會被轉成空 object。 |

### 7.2 已確認的 event 與 detail

| Event | 來源 | Detail 欄位 |
|---|---|---|
| `activate_skip` | `windows.py` **[S]** | `name`、`reason` |
| `activate` | `windows.py` **[S]** | `name`、`cold`；focus 不確定時另有 `warn` |
| `screenshot` | `capture.py` **[S]** | `app`、`window_id`、`path` |
| `click_text` | current architecture 文件 **[D]** | exact detail 未由本次 source 驗證 |
| `ensure_media_playing` | current architecture 文件 **[D]** | exact detail 未由本次 source 驗證 |

`detail` 可以包含 runtime app 名稱或檔案路徑，因此 audit log 本身應視為可能敏感。

## 8. Capture data

### 8.1 Screenshot result

`screenshot()` 回傳 PNG 檔案路徑字串。**[S]**

```text
CaptureResult = str
```

路徑可能由 caller 指定；預設檔名包含 process id 與 nanosecond timestamp，以降低並行覆蓋機率。PNG 旁邊沒有 companion metadata JSON。

### 8.2 `verify()` result

Skill contract 表示 `verify()` 會回傳可供 agent 讀取的 screenshot path。**[D]**

因此最低可描述為：

```text
VerifyResult = str
```

exact error envelope 與 annotation 欄位未由本次 source 驗證。

## 9. Daemon message

### 9.1 Request

`daemon.client_request()` 傳送單行 JSON object。**[S]**

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `op` | enum | 必有 | `ping`、`quit` 或 `exec`。 |
| `token` | `str` | 必有 | 與 daemon 端保存值相符的 opaque secret；文件不記錄內容。 |
| `code` | `str` | `exec` 時必有 | 要在 daemon namespace 中編譯與執行的 Python source。 |

### 9.2 Response

| 形式 | 欄位 |
|---|---|
| Ping success | `ok: true`、`pong: true` |
| Quit success | `ok: true` |
| Exec result | `ok: bool`、`stdout: str`、`stderr: str` |
| Protocol/auth/unknown-op error | `ok: false`、`error: str` |

注意：exec 失敗時仍回傳 `stdout`／`stderr`，而不是 protocol-level `error` object。

完整 schema 見 [`JSON-SCHEMAS.md`](./JSON-SCHEMAS.md)。

## 10. Voice tool data

### 10.1 Function tool definition

每個 `TOOL_DEFINITIONS` entry 的結構如下。**[S]**

```text
FunctionToolDefinition = {
  type: "function",
  name: str,
  description: str,
  parameters: JSONSchemaObject,
}
```

`parameters` 是 JSON Schema-like object：

```text
JSONSchemaObject = {
  type: "object",
  properties: object,
  required: string[],
}
```

各 property 可額外包含 `description`、`default` 等 annotation。

### 10.2 實際公開的 tool 名稱

| Tool | 參數 | 成功 result |
|---|---|---|
| `list_apps` | 無 | `list[{name, active}]`，最多 40 筆 |
| `open_app` | `name: str` | `AppInfo` |
| `screen_labels` | `app?: str`、`limit?: int` | `list[str]` |
| `click_text` | `text: str`、`app?: str` | AX hit-like value；exact shape 未驗證 |
| `type_text` | `text: str` | `{typed: int}` |
| `hotkey` | `keys: str[]` | `{keys: str[]}` |
| `move_mouse` | `x: number`、`y: number`、`duration?: number` | position-like value |
| `click_xy` | `x: number`、`y: number`、`double?: bool` | `{clicked: true}` |
| `mouse_pos` | 無 | position-like value |
| `wiggle_mouse` | 無 | helper result；exact shape 未驗證 |

`VOICE.md` 中列出的 design surface 與 current executable schema 不完全相同；本文件以上表的 `voice_tools.py` 實作為準。

### 10.3 Tool execution envelope

`voice_tools.execute()` 一律回傳 JSON 字串。**[S]**

```text
SuccessEnvelope = {
  ok: true,
  result: any,
}

ErrorEnvelope = {
  ok: false,
  error: str,
}
```

Dry-run 仍使用 success envelope，`result` 為：

```text
{
  dry_run: true,
  tool: str,
  arguments: object,
}
```

## 11. CLI 與診斷輸出

下列輸出為人類可讀文字，不是 JSON wire schema：

| 命令／helper | 輸出模型 |
|---|---|
| `--doctor` | line-oriented `PASS`／`FAIL` 檢查結果 |
| `selftest` | line-oriented `PASS`／`FAIL` 測試結果 |
| `demo` | 步驟式文字與數值 |
| `skill` | Markdown skill 文件 |
| 一般 stdin script | helper 寫入 stdout 的文字與 Python value representation |
| daemon status | 狀態文字；exact format 未由未提供的 `run.py` 驗證 |

## 12. 邏輯集合總表

| 集合／記錄 | 型別 | 持久化 | 排序／數量限制 |
|---|---|---|---|
| `list_apps()` | `list[AppInfo]` | 否 | active 優先、name 排序 |
| `list_windows()` | `list[WindowInfo]` | 否 | 過濾 layer 與尺寸 |
| `labels()` | `list[str]` | 否 | caller 可指定 limit |
| `ax_snapshot()` | `list[AxNode]` | 否 | caller 可指定 node 上限與 interactive-only |
| `media_transport()` | `MediaTransportState` | 否 | 單一狀態 |
| audit log | `list[AuditRow]` 的 append-only 串流 | 是，JSONL | 無輪替／無保留上限 |
| daemon exchange | request／response object | 僅傳輸 | 一個連線一個 request／response |
| voice tool exchange | call／output item | 僅傳輸 | scaffold 未設整體輪數上限 |
| screenshot | PNG binary | 是 | 每個預設路徑具唯一名稱 |
