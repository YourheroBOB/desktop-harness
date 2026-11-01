# CLI 參考：`desktop-harness`

`desktop-harness` 是產品的主要介面——**不是 MCP server**，而是一個本機 CLI（見 [ADR-0002](../fmb-adr/ADR-0002-cli-not-mcp.md)）。Agent 以 shell 呼叫，腳本透過 stdin（heredoc）餵入 Python。

進入點：`desktop_harness.run:main`（見 [pyproject.toml](../../pyproject.toml) `[project.scripts]`）。

## 全域行為

- **stdin 腳本模式**：不帶子命令時，CLI 從 stdin 讀取 Python 腳本，組裝 helper 命名空間（含 `agent-workspace/agent_helpers.py`）後執行。預設會自動改用常駐 daemon（若已在跑）；`DH_NO_DAEMON` 可强制本機行程。腳本的 stdout／stderr 會回傳給呼叫端。
- **版本**：`--version` 印出版本字串（目前 `0.4.2`，見 `src/desktop_harness/__init__.py`）。
- **結束碼**：成功為 `0`；健檢／自測有失敗項目時為非 0。

## 指令總覽

| 指令 | 用途 | 破壞性 |
|------|------|--------|
| `desktop-harness <<'PY' … PY` | 執行一段 Python 控制腳本 | 依腳本 |
| `desktop-harness --version` | 印出版本 | 無 |
| `desktop-harness --doctor` | 權限與環境健檢 | 無 |
| `desktop-harness selftest` | 非破壞性自我測試 | 低（會動滑鼠／開 TextEdit） |
| `desktop-harness demo` | 可見煙霧測試 | 中（移動真實滑鼠、開 TextEdit、打字） |
| `desktop-harness skill` | 輸出 `SKILL.md` 到 stdout | 無 |
| `desktop-harness daemon start [--bg]` | 啟動常駐 daemon | 無 |
| `desktop-harness daemon status` | 查詢 daemon 狀態 | 無 |
| `desktop-harness daemon stop` | 停止 daemon | 無 |
| `desktop-harness check-update` | 與 GitHub main 比對版本 | 無（需網路） |

---

## stdin 腳本模式

```bash
desktop-harness <<'PY'
print(mouse_pos())
open_app("Safari")
print(labels()[:10])
PY
```

- **說明**：預設路由到常駐 daemon（較快）；daemon 未啟動或 `DH_NO_DAEMON` 啟用時改為本機行程。
- **前置條件**：已授予 Accessibility（讀 AX、注入鍵鼠）；截圖另需 Screen Recording。
- **錯誤**：敏感 app 被阻擋時拋 `PermissionError`（見 [configuration.md](./configuration.md) `DH_ALLOW_SENSITIVE`）。

## `--version`

- **用途**：印出目前已安裝版本。
- **用法**：`desktop-harness --version`
- **回傳**：版本字串（stdout）。

## `--doctor`

- **用途**：驗證 PyObjC 載入、Accessibility（`AXIsProcessTrusted`）、Screen Recording（實拍一張並驗證檔案大小）、前景 app AX 節點數、視窗列表（對應 `admin.run_doctor()`）。
- **用法**：`desktop-harness --doctor`
- **副作用**：會嘗試截一張圖（非破壞）。
- **回傳／結束碼**：逐項印 PASS／FAIL；全過為 `0`，否則非 0。

## `selftest`

- **用途**：非破壞性自測——先跑 doctor，再測核心 helper、滑鼠移動後復原、截圖、`media_transport` API、`find_app` 排序、`frame_on_screen`、TextEdit 開啟＋打字、daemon 背景啟動與 exec 往返（對應 `selftest.run_selftest()`）。
- **用法**：`desktop-harness selftest`
- **副作用**：會移動真實滑鼠並開啟 TextEdit；daemon 往返測試可能影響你已在跑的 daemon（測試隔離議題，見 [fmb-perf TR-6](../fmb-perf/findings-timeouts-recovery.md)）。
- **結束碼**：全過為 `0`，否則非 0。

## `demo`

- **用途**：可見煙霧測試——開 TextEdit、`cmd+n`、移滑鼠進視窗、`wiggle`、`click`、打字、印 labels，最後收起 presence（對應 `demo.run_demo()`）。
- **用法**：`desktop-harness demo`
- **副作用**：**會移動你的真實滑鼠並開啟 TextEdit**；需人工觀看。
- **回傳**：`0`。

## `skill`

- **用途**：把內建 `SKILL.md` 輸出到 stdout，供安裝腳本註冊 Grok skill（`install.sh` 會導向 `~/.grok/skills/desktop-harness/SKILL.md`）。
- **用法**：`desktop-harness skill > ~/.grok/skills/desktop-harness/SKILL.md`

## `daemon`（子命令）

常駐溫熱进程，讓多步任務不必重複 import PyObjC。協定細節見 [daemon-protocol.md](./daemon-protocol.md)。

| 子命令 | 說明 |
|--------|------|
| `daemon start` | 前景啟動 daemon |
| `daemon start --bg` | 背景啟動 daemon |
| `daemon status` | 回報是否運行、PID |
| `daemon stop` | 停止 daemon |

- **安全**：socket 與 token 檔皆為 `0600`；僅同 UID 可用。多人共用機器請勿常開（見 [SECURITY.md](../../SECURITY.md)）。
- **建議**：長会话結束後 `desktop-harness daemon stop`。

## `check-update`

- **用途**：將本機版本與 GitHub `main` 比對（選用）。**不會**自動更新——會動滑鼠的程式碼更新由使用者自己決定。
- **用法**：`desktop-harness check-update`
- **前置條件**：需可連線 GitHub。

<<<END_FILE>

<<<FILE docs/fmb-api/helpers.md>>>
# 公開 Helper 函式參考（`desktop_harness.helpers`）

這些函式會在 stdin 腳本模式下自動注入命名空間，可直接呼叫；`agent-workspace/agent_helpers.py` 的自訂 wrapper 也會一併載入。

> **簽名來源**：依據 `README.md`、`SKILL.md`、`DESIGN.md`、`docs/fmb/ARCHITECTURE*.md`、`HOW_IT_WORKS.md`、`VOICE.md` 與呼叫點（`demo.py`、`scripts/observe-demo.sh`、`scripts/voice_session.py`）整理。精確型別與預設值以 `src/desktop_harness/` 為準；不確定處以「依實作」標注。

## 總覽

| 類別 | 函式 |
|------|------|
| 探索與視窗 | `list_apps`、`list_windows`、`frontmost_app`、`find_app`、`open_app`、`activate` |
| 感知（AX） | `labels`、`button_labels`、`ax_snapshot`、`find`、`press_element`、`set_element_value`、`frame_on_screen` |
| 依名稱操作 | `click_text`、`set_field` |
| 媒體 | `media_transport`、`ensure_media_playing` |
| 滑鼠 | `mouse_pos`、`move_to`、`move_by`、`wiggle`、`click`、`right_click`、`click_frame`、`drag`、`scroll` |
| 鍵盤 | `type_text`、`hotkey`、`key` |
| 截圖 | `screenshot`、`window_info` |
| Presence | `enable_agent_cursor`、`hide_agent_presence` |
| 後設／驗證 | `wait`、`wait_stable`、`verify` |

---

## 探索與視窗（Discovery & Windows）

### `frontmost_app()`
- **說明**：取得目前前景 app 名稱（NSWorkspace）。
- **回傳**：`str`；無法取得時可能為 `None`。
- **錯誤**：未授權 Accessibility 時可能取不到。
- **範例**：
  ```python
  print(frontmost_app())
  ```

### `list_apps()`
- **說明**：列出執行中的 app 名稱。
- **回傳**：`list[str]`。

### `list_windows()`
- **說明**：以 `CGWindowList` 列出現有視窗。
- **回傳**：`list[dict]`；每個項目至少含 `app`、`x`、`y`、`w`、`h`（其餘欄位依實作）。
- **範例**：
  ```python
  wins = [w for w in list_windows() if w["app"] == "TextEdit"]
  if wins:
      w = wins[0]
      cx, cy = w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
  ```

### `find_app(name)`
- **說明**：以「精確 → 前綴 → 最短子字串 → bundle id」的權重搜尋 app；`selftest` 另涵蓋以 PID 指定的路徑。
- **參數**：`name: str`。
- **回傳**：app 記錄（`dict`）或 `None`。
- **範例**：`print(find_app("TextEdit"))`

### `open_app(name)`
- **說明**：啟動或聚焦 app（內部走 `windows.activate`：先試 `NSRunningApplication`，必要時以 `open -a` 備援，並輪詢確認成為前景）。
- **參數**：`name: str`。
- **回傳**：成功時回傳對應 app 資訊（結構依實作）。
- **錯誤**：命中敏感 app 阻擋時拋 `PermissionError`（見 [configuration.md](./configuration.md)）。
- **範例**：`open_app("TextEdit")`

### `activate(app_or_name)`
- **說明**：將目標 app 帶到前景；已在前景則跳過，事後確認焦點。`open_app` 為其加上安全閘門的較高層包裝。
- **參數**：`app_or_name`（app 記錄或名稱）。
- **錯誤**：敏感 app 阻擋時拋 `PermissionError`。

---

## 感知（Perception / AX）

### `labels(app=None)`
- **說明**：取得（可互動）UI 元件的標籤文字，AX 優先的主要「眼睛」。
- **參數**：`app: str | None`（省略取前景）。
- **回傳**：`list[str]`。
- **範例**：
  ```python
  print(labels()[:15])
  print(labels("TextEdit")[:8])
  ```

### `button_labels(app=None)`
- **說明**：只取出按鈕類（`AXButton`）元件的標籤。
- **回傳**：`list[str]`。

### `ax_snapshot(app=None, *, interactive_only=True, max_nodes=…)`
- **說明**：回傳緊湊的互動節點快照（`role`、`title`、`value`、`frame` 等）。`max_nodes` 用於限制樹大小（避免傾印整棵 AX）。快取鍵為 `(pid, interactive_only, max_nodes)`。
- **回傳**：`list[dict]`（節點屬性）。
- **範例**：`for n in ax_snapshot(interactive_only=True): print(n.get("role"), n.get("title"))`

### `find(query, *, role=None, exact=False, app=None)`
- **說明**：以標題／標籤在 AX 樹中找最佳匹配；評分偏好「完全相等 > 短字詞」，可避開 `Play` vs `Play all`／`Playing from` 這類誤判（見 [POSTMORTEM](../POSTMORTEM-media-play.md)）。
- **參數**：`query: str`；`role`（如 `"AXButton"`）；`exact: bool` 完全比對；`app`。
- **回傳**：節點（`dict`）或 `None`。

### `press_element(element)`
- **說明**：對 AX 節點執行 `AXPress`（元素動作優先於座標點擊）。
- **參數**：`element`（`find`／`ax_snapshot` 回傳的節點）。

### `set_element_value(element, value)`
- **說明**：以 `AXSetAttributeValue` 設定節點值。
- **參數**：`element`、`value`。

### `frame_on_screen(frame)`
- **說明**：判斷給定 frame 是否落在可見螢幕範圍（多螢幕座標轉換未保證，見已知限制）。
- **回傳**：`bool`。

---

## 依名稱操作（Act by name）

### `click_text(text, app=None, *, role=None, exact=False)`
- **說明**：以標籤找到元件後優先 `AXPress`；無 AX 動作時退回點擊該 frame 中心。
- **參數**：`text: str`；`app`；`role`；`exact: bool`（播放／暫停等請用 `exact=True`）。
- **回傳**：是否找到並動作（`bool`，結構依實作）。
- **提醒**：這是「變更畫面」的操作，之後必須 `verify()`（[ADR-0009](../fmb-adr/ADR-0009-verify-after-mutation.md)）。
- **範例**：
  ```python
  click_text("Format")
  click_text("Play", role="AXButton", exact=True)
  verify("播放器開始播放")
  ```

### `set_field(label, value, app=None)`
- **說明**：以標籤找到輸入欄並設定其值（AX set value 路徑）。
- **參數**：`label: str`、`value`、`app`。
- **提醒**：同屬變更畫面操作，之後請 `verify()`。

---

## 媒體（Media）

### `media_transport(app=None)`
- **說明**：讀取播放器 AX 狀態，**只讀不動作**。
- **回傳**：`dict`，含 `state`（`playing`／`paused`／`unknown`）與 `transport_play`、`row_play`、`play` 等訊號。
- **範例**：`print(media_transport())`

### `ensure_media_playing(app=None)`
- **說明**：look-once／act-once——若已看到 Pause（正在播放）則不做任何事；僅在暫停時按一次精確 Play，再讀一次狀態確認。**絕不**連按空白鍵。
- **回傳**：結果狀態（`dict`，依實作）。
- **範例**：
  ```python
  state = media_transport()
  if state.get("state") == "paused":
      ensure_media_playing()
      verify("播放器開始播放")
  ```

---

## 滑鼠（Mouse / `input.py`）

> 皆驅動**真實系統游標**（`CGWarpMouseCursorPosition` + `CGEventPost`）。`duration` 為動畫時長（秒）；省略時依預設速度，`DH_MOUSE_INSTANT` 可改為瞬移。

### `mouse_pos()`
- **回傳**：目前游標座標 `(x, y)`。

### `move_to(x, y, duration=None)`
- **說明**：將游標移動到座標。
- **範例**：`move_to(400, 300)`、`move_to(400, 300, duration=0.4)`

### `move_by(dx, dy, duration=None)`
- **說明**：相對位移微調。

### `wiggle(amplitude=…, cycles=…, duration=…)`
- **說明**：小幅抖動，可作為「思考中」的視覺提示。
- **範例**：`wiggle(amplitude=14, cycles=2, duration=0.4)`

### `click(x, y, duration=None)`
- **說明**：移動並左鍵點擊。
- **範例**：`click(520, 420, duration=0.1)`

### `right_click(x, y, duration=None)`
- **說明**：右鍵（開啟內容選單）。

### `click_frame(frame)`
- **說明**：點擊某個 AX frame 的中心。

### `drag(x1, y1, x2, y2, duration=None)`
- **說明**：按下滑鼠並拖曳到目標座標。

### `scroll(dy, dx=…)`
- **說明**：滾輪捲動；水平捲動參數依實作。

---

## 鍵盤（Keyboard / `input.py`）

### `type_text(text)`
- **說明**：輸入 Unicode 文字（逐字送出鍵盤事件；長字串每字約有固定延遲，見路線圖剪貼簿規劃）。
- **範例**：`type_text("hello")`

### `hotkey(*keys)`
- **說明**：組合快捷鍵。
- **範例**：`hotkey("cmd", "n")`、`hotkey("cmd", "s")`

### `key(name)`
- **說明**：送出單一按鍵（如 `return`、`tab`、`esc`；命名慣例依實作）。

---

## 截圖（Capture / `capture.py`）

### `screenshot(app=None, …)`
- **說明**：視窗或主畫面截圖為 PNG；每次呼叫產生唯一檔名（含 PID 與 `time_ns`），避免併發覆蓋。
- **參數**：`app`（指定則視窗層級）；region／display 等依實作。
- **回傳**：PNG 檔案路徑（`str`）。
- **錯誤**：前景為敏感 app 時阻擋截圖（除非 `DH_ALLOW_SENSITIVE`）；未授權 Screen Recording 時可能得到全黑或過小檔案。
- **範例**：
  ```python
  path = screenshot(app="TextEdit")
  print(path)  # 以視覺讀取該 PNG 驗證
  ```

### `window_info(…)`
- **說明**：低階視窗中繼資料（依實作）。

---

## Presence（視覺提示）

> 單一系統游標 + 藍色移動光環 + 紅色點擊快閃 + 底部「Agent active — hands off」橫幅；`DH_PRESENCE=0` 可關閉。AppKit 嚴格 main-thread，閒置期間以 `keep_alive()` 分片 pump（見 [ADR-0006](../fmb-adr/ADR-0006-appkit-main-thread.md)）。

### `enable_agent_cursor(on)`
- **說明**：開／關 agent 游標光環。
- **範例**：`enable_agent_cursor(True)`

### `hide_agent_presence()`
- **說明**：在一段操作結束時收起 presence。

---

## 後設／驗證（Meta）

### `wait(seconds)`
- **說明**：固定等待（秒）。
- **範例**：`wait(0.5)`

### `wait_stable(…)`
- **說明**：等待 UI 穩定（逾時等參數依實作）。

### `verify(note, app=None)`
- **說明**：對「意在改變畫面」的动作收尾——截圖並回傳路徑，讓 agent 以視覺確認。純探索呼叫不需 verify。被敏感閘門擋下時 verify 會失敗（正確行為）。
- **參數**：`note: str`（預期發生什麼，供人阅读）；`app`。
- **回傳**：截圖路徑（`str`）。
- **範例**：`verify("TextEdit 出現輸入的文字")`

---

## 模組級常數與物件

- `desktop_harness.__version__`：版本字串（`0.4.2`）。
- 語音相關 `TOOL_DEFINITIONS`、`SESSION_INSTRUCTIONS`、`execute()`：見 [voice-tools.md](./voice-tools.md)。
- 本公開介面以**函式**為主；提供的材料中未記錄需對外使用的公開類別。

---

## 尚未實作（路線圖，非目前 API）

以下為規劃項，**現在呼叫會找不到**：`wait_for(...)`、`menu_click(...)`、剪貼簿 `get_clipboard`／`set_clipboard`／`paste`、背景不搶焦控制、MCP wrapper。見 [ROADMAP.md](../fmb/ROADMAP.md)。
