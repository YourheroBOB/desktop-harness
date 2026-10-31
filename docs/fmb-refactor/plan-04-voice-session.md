# 批次 4：`scripts/voice_session.py` 拆分與型別一致化

- **範圍：** `scripts/voice_session.py`（僅此一檔；`voice_tools.py` 未直接檢視，涉及處先以特徵測試釘住）
- **風險：** 中（實驗性腳本、無既有測試、依賴行為只能靠 dry-run 離線驗證）
- **對應 findings：** D4、D5、L2、N4、C5
- **行為變更：** dry-run demo 傳給 `execute()` 的引數從 dict 改為 JSON 字串（與 live 路徑一致 — 見 §1.3，需先釘住現況再決定統一方向）

## 1. 重構前問題

### 1.1 重複 import 與未使用符號（D4）

`main()` 與 `run_session()` 各自 `from desktop_harness.voice_tools import SESSION_INSTRUCTIONS, TOOL_DEFINITIONS, execute`；`main()` 的 `SESSION_INSTRUCTIONS` 從未使用。

### 1.2 `run_session()` 過長、職責混雜（L2 / D5）

單一 async 函式做：連線、`session.update` 組裝、文字 turn、事件分發（巢狀 elif 鏈）、工具執行、`function_call_output` 回送、`response.done` 續 turn。`json.dumps({"type": "conversation.item.create", …})` 組裝重複兩次。

### 1.3 `execute()` 引數型別不一致（N4 / C5）

live 路徑：

```python
arguments = event.get("arguments") or "{}"   # JSON 字串
result = execute(name, arguments, dry_run=dry_run)
```

dry-run demo：

```python
out = execute(name, args_, dry_run=False)    # dict！
```

`voice_tools.execute` 的簽名未直接檢視 — 兩條路徑傳不同型別，至少其中一條與 `execute` 的預期不符，或 `execute` 內部有寬容處理。**動手前必須先讀 `voice_tools.py` 並以測試釘住**（統一方向見 §3 步驟 2）。

## 2. 需先補的測試（動手前）

全部**離線、零網路**（`XAI_API_KEY` 一律 `FAKE_VALUE_FOR_TEST`，絕不連 `api.x.ai`）：

1. **讀 `voice_tools.execute` 原始碼確認簽名**，寫特徵測試：分別以 dict 與 JSON 字串呼叫，記錄現況行為（何者正常、何者丟錯）。這決定 §1.3 的統一方向。
2. `_send_json` / `_tool_output_item`（新抽出的純組裝函式）：輸出 dict 結構與重構前 inline `json.dumps` 的內容逐鍵相等。
3. 事件分派：抽出 `_handle_function_call` 後，以假 ws 物件（記錄 `send` 呼叫）驗證收到 `response.function_call_arguments.done` 事件時會送出正確的 `function_call_output` item 並 append `pending_calls`。
4. `--list-tools`：輸出非空且含工具名（此路徑本來就離線）。
5. dry-run demo 路徑：monkeypatch `execute` 後跑 `--dry-run`（無 key 分支），斷言三個 demo 呼叫的引數型別一致。

## 3. 重構步驟

1. 補 §2 測試。
2. **統一 `execute()` 引數型別**：以 §2.1 的特徵測試結果為準 — 若 `execute` 預期 JSON 字串（依 live 路徑推測最可能），dry-run demo 改傳 `json.dumps(demo_args)`；若預期 dict，live 路徑改 `json.loads`。**保守原則：改呼叫端、不改 `voice_tools.py`**（該檔未檢視，不在本批範圍）。
3. import 收斂：模組頂端（`sys.path` 設定之後）import 一次；`main()` 不再重複 import、不再 import 未使用的 `SESSION_INSTRUCTIONS`。
4. 抽出純組裝函式 `_send_json(ws, payload)`、`_tool_output_item(call_id, output)`。
5. 抽出 `async def _handle_function_call(ws, event, *, dry_run) -> str | None`（回傳 call_id）；`run_session()` 的迴圈只剩分派骨架。
6. `et` → `event_type`、`args_` → `demo_args`（N4）。
7. dry-run + `--text` 假 WS 驗證（本機臨時 port 起 `websockets.serve` 假 server，同 fmb-perf verification-plan §2 TR 批次的做法）。

## 4. 重構前後對照

### 4.1 重複的 JSON 組裝（D5）

重構前（兩處）：

```python
await ws.send(json.dumps({
    "type": "conversation.item.create",
    "item": {
        "type": "function_call_output",
        "call_id": call_id,
        "output": result,
    },
}))
```

重構後：

```python
def _tool_output_item(call_id: str, output: str) -> dict:
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        },
    }

async def _send_json(ws, payload: dict) -> None:
    await ws.send(json.dumps(payload))
```

### 4.2 工具呼叫處理（L2）

重構後（`run_session()` 迴圈內）：

```python
elif event_type == "response.function_call_arguments.done":
    call_id = await _handle_function_call(
        ws, event, dry_run=dry_run)
    if call_id:
        pending_calls.append(call_id)
```

`_handle_function_call` 內：解析 name/call_id/arguments → `execute` → 印 `[tool]`/`[tool result]` → `_send_json(ws, _tool_output_item(call_id, result))` → 回傳 call_id。

### 4.3 dry-run demo 引數（N4 / C5）

重構後（假設 §3.2 判定 `execute` 預期 JSON 字串）：

```python
demos = [
    ("list_apps", {}),
    ("mouse_pos", {}),
    ("screen_labels", {"limit": 10}),
]
for name, demo_args in demos:
    out = execute(name, json.dumps(demo_args), dry_run=False)
    print(f"\n>> {name} {demo_args}\n{out[:500]}")
```

> 若特徵測試顯示 `execute` 預期 dict，則反方向統一（live 路徑 `json.loads`），原則不變：兩條路徑傳**同一型別**，並以測試釘死。

## 5. 驗證方式（本批獨立驗收）

1. §2 離線測試全綠（假 WS server 於 127.0.0.1 臨時 port，測試自起自收）。
2. `python scripts/voice_session.py --list-tools` 正常。
3. `XAI_API_KEY=FAKE_VALUE_FOR_TEST python scripts/voice_session.py --dry-run` — 走本地 demo 分支、零網路連線（可用 `--text` + 假 WS 或確認無 key 分支不 import websockets）。
4. `--dry-run` 與 live 的工具呼叫引數型別經測試斷言一致。

## 6. 風險與回滾

- **最大不確定因子是 `voice_tools.execute` 簽名未檢視** — 已以「先讀檔 + 特徵測試」為硬性前置步驟消除；若兩種型別都能跑（內部寬容處理），統一為字串（與 live 一致，呼叫端改動最小）。
- voice 是 experimental 表面（review #22、ROADMAP「非目標」），破壞影響面小；但正因如此**不**在本批順手修 TR-1/2/3（WS timeout、async 阻塞、無限續 turn）— 那些是行為修復，屬 fmb-perf。
- 續 turn 邏輯（`response.done` + `pending_calls`）**逐字保留**，只搬位置不改判斷。
- 回滾：單一 PR revert。
