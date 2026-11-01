# 實驗性語音工具參考（Voice Tools）

**狀態：實驗性（scaffold）。** 非核心安裝路徑的一部分；需要另行安裝 `websockets`、`sounddevice`、`numpy`，並提供 `XAI_API_KEY`（與 Grok Build 登入不同，見 [VOICE.md](../../VOICE.md)）。無金鑰時可用 `--dry-run` 離線檢視工具。

> 本文件不出現任何真實金鑰；需要假憑證時一律使用 `FAKE_VALUE_FOR_TEST`。

## 網路端點（唯一的對外連線）

- **WebSocket**：`wss://api.x.ai/v1/realtime?model=<model>`
  - 預設模型：`grok-voice-think-fast-2.0`；可以 `GROK_VOICE_MODEL` 覆寫（見 [configuration.md](./configuration.md)）。
  - 認證：`Authorization: Bearer <XAI_API_KEY>`（**只寫變數名，值不放檔案**）。
- 核心桌面控制**零網路**；此端點僅供實驗性語音。`check-update` 另會連 GitHub 比對版本。

## Python API（`desktop_harness.voice_tools`）

| 物件 | 型別 | 說明 |
|------|------|------|
| `TOOL_DEFINITIONS` | `list[dict]` | 送給 Realtime 的工具 schema 清單；每項至少含 `name`、`description`（及參數 schema）。 |
| `SESSION_INSTRUCTIONS` | `str` | 給語音模型的系統指令。 |
| `execute(name, arguments, *, dry_run=False)` | `-> str` | 本機執行器：依工具名分派對應 harness helper。`arguments` 可為 `dict` 或 JSON 字串；回傳字串（會作為 `function_call_output` 回傳給模型）。 |

- **範例**：
  ```python
  from desktop_harness.voice_tools import TOOL_DEFINITIONS, execute
  for t in TOOL_DEFINITIONS:
      print(t["name"])
  print(execute("mouse_pos", {}, dry_run=False))
  ```

## 工具清單（對應 harness helper）

| 工具 | 對應 |
|------|------|
| `list_apps` | `list_apps()` |
| `open_app` | `open_app(name)` |
| `screen_labels` | `labels(app?)` |
| `click_text` | `click_text(text, app?)` |
| `type_text` | `type_text(text)` |
| `hotkey` | `hotkey(*keys)` |
| `move_mouse` | `move_to(x, y)` |
| `click_xy` | `click(x, y)` |
| `screenshot_app` | `screenshot(app=…)`（僅回傳路徑） |
| `run_shell` | 選用、高風險——**預設關閉** |

## `scripts/voice_session.py` CLI

| 旗標 | 說明 |
|------|------|
| `--dry-run` | 不連線、不動真實 GUI；僅在本機示範工具執行器。 |
| `--text "…"` | 單輪文字對話（不需麥克風）。 |
| `--list-tools` | 印出工具名與簡述。 |

- 無 `XAI_API_KEY` 且未加 `--dry-run`：清楚印出提示並以結束碼 `2` 退出（不假裝有權限）。
- 麥克風串流在此 scaffold 尚未接線；請以 `--text` 測試工具呼叫。

## 同意／安全（Consent）

- 會**送出訊息、付款、刪除、變更安全設定**的工具必須先向使用者確認，否則拒絕。
- `run_shell` 屬高風險、預設關閉；語音場景尤其要避免「try everything」式連鎖動作。
- 一般 harness 安全規則（敏感 app 阻擋、verify-after-mutation）同樣適用，見 [ADR-0008](../fmb-adr/ADR-0008-sensitive-app-gates.md)、[ADR-0009](../fmb-adr/ADR-0009-verify-after-mutation.md) 與 [SKILL.md](../../SKILL.md)。
