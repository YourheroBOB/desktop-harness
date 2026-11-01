# 審查發現：`scripts/voice_session.py`

> 行號以 v0.4.2 快照為準（全檔 177 行）。錨點建議搭配 `grep -n` 確認。
> 嚴重度：P1 = 正確性／隱私／可靠性明顯缺陷；P2 = 打磨項。

---

## VS-1｜`--dry-run` 其實會動真實 GUI（唯讀），與 help 文字不符

- **位置：** `scripts/voice_session.py:31`（help 文字）、`:61-73`（dry-run 分支）、`:70`（`dry_run=False`）
- **嚴重度：** P1（正確性／安全語意）
- **說明：** help 與 docstring 宣稱 `--dry-run` 「Execute no real GUI」，但無 key 的 dry-run 路徑呼叫 `execute(name, args_, dry_run=False)`，只是剛好 demo 清單（`list_apps`/`mouse_pos`/`screen_labels`）全是唯讀才沒出事。這是一顆定時炸彈：任何人往 `demos` 清單加一個 `open_app` 或 `click_text`，「模擬模式」就會真的操作桌面，而使用者以為自己在安全模式。語意分裂也讓 review 無法一眼判斷 dry-run 是否安全。
- **建議修法：**

```python
READ_ONLY_TOOLS = {"list_apps", "frontmost_app", "mouse_pos", "screen_labels"}

if args.dry_run and not key:
    for name, args_ in demos:
        if name not in READ_ONLY_TOOLS:
            raise SystemExit(f"dry-run demo list must stay read-only; {name!r} refused")
        out = execute(name, args_, dry_run=True)   # 保守：dry-run 永不碰真實 GUI
```

同時把 help 改成：「--dry-run: 不執行任何真實 GUI 動作（僅離線檢視工具）」。
- **工作量：** S（≤2h）

---

## VS-2｜工具參數／結果原樣印出，機密內容進終端機 scrollback 與 log

- **位置：** `scripts/voice_session.py:153`（`print(f"\n[tool] {name}({arguments})")`）、`:155`（`print(f"[tool result] {result[:300]}")`）
- **嚴重度：** P1（隱私）
- **說明：** `type_text("…")`、`hotkey(...)`、`set_field(...)` 的 arguments 會把使用者即將輸入的內容原樣印出——可能是密碼、個資、訊息內文。工具結果（`screen_labels`）同樣可能包含螢幕上的私人資訊（郵件主旨、聊天對象）。這直接違反 SKILL.md「audit 只記長度不記內容」與本 repo 的安全立場；終端機 scrollback、CI log、螢幕錄影都會留存。
- **建議修法：**

```python
_SENSITIVE_TOOLS = {"type_text", "hotkey", "key", "set_field", "run_shell"}

def _safe_preview(name: str, arguments: str, limit: int = 80) -> str:
    if name in _SENSITIVE_TOOLS:
        try:
            payload = json.loads(arguments)
            n = len(payload.get("text") or json.dumps(payload))
        except Exception:
            n = len(arguments)
        return f"<redacted {name}: {n} chars>"
    return arguments[:limit]

print(f"\n[tool] {name}({_safe_preview(name, arguments)})")
...
print(f"[tool result] {result[:300] if name not in _SENSITIVE_TOOLS else '<redacted>'}")
```

詳細輸出改由 `--verbose` 開啟，並在文件明言「verbose 輸出可能含螢幕內容，勿在分享畫面時開啟」。
- **工作量：** S（2–3h，含文件）

---

## VS-3｜同步 `execute()` 阻塞 event loop，長動作卡死 WS／音訊串流

- **位置：** `scripts/voice_session.py:154`
- **嚴重度：** P1（併發）
- **說明：** `execute()` 是同步 GUI 呼叫（AX 走訪、滑鼠動畫、截圖），在 `async for` 迴圈內直接跑會阻塞整個 event loop：WS ping/pong 停擺、音訊 buffer 無人讀、server VAD 超時。長期後果是連線被 server 端踢掉或收音爆音。與 fmb-perf TR-2 同一根因。
- **建議修法：**

```python
result = await asyncio.wait_for(
    asyncio.to_thread(execute, name, arguments, dry_run=dry_run),
    timeout=float(os.environ.get("GROK_VOICE_TOOL_TIMEOUT", "30")),
)
```

`asyncio.TimeoutError` 時回一筆 `function_call_output` 告知模型「工具逾時」，而不是靜默卡住。注意：GUI 動作本質仍是前景導向，thread 只負責「不擋住網路」，不解決併發操控（見 ADR-0006 對 AppKit 的限制——presence 相關呼叫不可放到背景執行緒）。
- **工作量：** S（3–4h，含逾時行為測試）

---

## VS-4｜連線與事件迴圈都沒有逾時，網路異常時無限掛死

- **位置：** `scripts/voice_session.py:94-98`（`websockets.connect` 無 `open_timeout`）、`:131`（`async for raw in ws` 無 idle timeout）
- **嚴重度：** P1（逾時／可靠性）
- **說明：** DNS 黑洞、proxy 掛起、server 收完 session.update 後不回應——任何一種都讓行程永久停住，沒有輸出、沒有退出碼。使用者只能 Ctrl-C。腳本沒有任何逾時常數可調。
- **建議修法：**

```python
async with websockets.connect(
    WS_URL,
    additional_headers=headers,
    max_size=8 * 1024 * 1024,
    open_timeout=10.0,
    close_timeout=5.0,
    ping_interval=20.0,
    ping_timeout=20.0,
) as ws:
    IDLE = float(os.environ.get("GROK_VOICE_IDLE_TIMEOUT", "120"))
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=IDLE)
        except asyncio.TimeoutError:
            print(f"no event for {IDLE:.0f}s — closing session", file=sys.stderr)
            break
        ...  # 原有事件處理
```

`async for` 改成 `while True + recv()` 是為了能包 `wait_for`；其餘邏輯不變。
- **工作量：** S（2–3h）

---

## VS-5｜事件迴圈零錯誤處理，任何例外都是 raw traceback

- **位置：** `scripts/voice_session.py:134`（`json.loads`）、`:131-172`（整個 `async for`）
- **嚴重度：** P2（錯誤處理）
- **說明：** 伺服器送來壞 JSON、連線中途關閉（401 無效 key 時最常見）、工具拋出 `PermissionError`（安全閘門）——全部變成未捕捉例外噴 stack trace，沒有分類、沒有 audit、沒有可讀的 exit code。使用者無法分辨「key 錯了」vs「網路斷了」vs「被安全閘門擋了」。
- **建議修法：**

```python
try:
    while True:
        ...
except websockets.ConnectionClosed as e:
    print(f"connection closed: {e}", file=sys.stderr)
    return 2
except json.JSONDecodeError as e:
    print(f"bad frame from server: {e}", file=sys.stderr)
    continue
except Exception as e:
    print(f"session error: {type(e).__name__}: {e}", file=sys.stderr)
    return 1
```

並把錯誤分類（auth / network / protocol / tool-blocked）寫進 stderr 前綴，方便 grep。
- **工作量：** S（2h）

---

## VS-6｜自動續 turn 無上限，可能無限燒 API 額度

- **位置：** `scripts/voice_session.py:130`（`pending_calls`）、`:165-169`（`response.done` → `response.create`）
- **嚴重度：** P2（併發／成本）
- **說明：** 每次 `response.done` 且 `pending_calls` 非空就再送一次 `response.create`。若模型每輪都產生工具呼叫（例如 `screen_labels` 迴圈），就是無限續航，每分鐘計費的 Voice API 會穩定燒錢，且沒有任何停止條件。
- **建議修法：**

```python
MAX_TURNS = int(os.environ.get("GROK_VOICE_MAX_TURNS", "8"))
turns = 0
...
elif et == "response.done":
    if pending_calls and turns < MAX_TURNS:
        turns += 1
        await ws.send(json.dumps({"type": "response.create"}))
        pending_calls.clear()
    elif pending_calls:
        print(f"max turns ({MAX_TURNS}) reached — stopping", file=sys.stderr)
        break
```

與 fmb-perf TR-3 同一問題，此處補上實作層修法。
- **工作量：** S（1h）

---

## VS-7｜`arguments` 型別契約待確認（可能把 JSON 字串當 dict 傳）

- **位置：** `scripts/voice_session.py:152-154`
- **嚴重度：** P2（正確性，**待確認**）
- **說明：** WS 事件的 `arguments` 是 JSON **字串**，程式直接傳給 `execute(name, arguments, dry_run=dry_run)`。若 `voice_tools.execute()` 預期簽名是 `dict`（大多數 tool executor 會），這裡每次呼叫都會炸或靜默失敗；若它內部自己 `json.loads`，則沒問題。`voice_tools.py` 未在本次視野內，無法斷言。
- **建議修法（不論契約為何都成立）：**

```python
try:
    payload = json.loads(arguments) if isinstance(arguments, str) else arguments
    if not isinstance(payload, dict):
        payload = {}
except json.JSONDecodeError:
    payload = {}
result = execute(name, payload, dry_run=dry_run)
```

並在 `voice_tools.execute` docstring 明寫接受的型別；加一個單測把「字串 arguments」與「dict arguments」都跑過。
- **工作量：** S（1–2h，含單測）

---

## VS-8｜無 `--text` 時掛住不走：server_vad 開了但沒有麥克風串流

- **位置：** `scripts/voice_session.py:104-105`（`turn_detection: server_vad`）、`:121-128`（else 分支只 print）
- **嚴重度：** P2（可用性）
- **說明：** 不帶 `--text` 執行時，session 開成 server VAD（等伺服器送音訊事件），但腳本沒有麥克風串流（docstring 自己說 "not wired in this scaffold yet"）。結果：print 一段提示後行程進入 `async for` 死等，看起來像當機。
- **建議修法：** 要嘛失敗得快——無 `--text` 且未實作收音時直接 `sys.exit(2)` 並印「mic streaming not implemented; use --text」；要嘛加 `--listen` 明確 opt-in 無限監聽。保守採前者。
- **工作量：** S（1h）

---

## VS-9｜`GROK_VOICE_MODEL` 未驗證直插 URL query

- **位置：** `scripts/voice_session.py:25-26`
- **嚴重度：** P2（相依風險／健壯性）
- **說明：** 環境變數直接 f-string 進 URL。含 `?`、`&`、空格或非 ASCII 的模型名會產生畸形 URL 或悄悄改到其他 endpoint。模型名同時也是「計費主體」，拼錯不會報錯只會 404。
- **建議修法：**

```python
from urllib.parse import quote
MODEL = os.environ.get("GROK_VOICE_MODEL", "grok-voice-think-fast-2.0")
WS_URL = f"wss://api.x.ai/v1/realtime?model={quote(MODEL, safe='')}"
```

可選：allowlist 比對已知模型，未知時 warn。
- **工作量：** S（0.5h）

---

## VS-10｜`execute`／ws 工廠未注入，難以離線單測

- **位置：** `scripts/voice_session.py:84-98`（`run_session` 內部直接 import 與 connect）
- **嚴重度：** P2（可測試性）
- **說明：** `run_session` 在函式內 `import websockets`、直接 `websockets.connect`、直接調用模組級 `execute`。測試只能靠真連線或 monkeypatch 全域，導致「VS-1..VS-9 全部修完也沒人測」。
- **建議修法：** 參數化：

```python
async def run_session(api_key, *, text=None, dry_run=False,
                      connect=websockets.connect, executor=execute, url=WS_URL):
    async with connect(url, ...) as ws:
        ...
        result = await asyncio.wait_for(asyncio.to_thread(executor, name, payload, dry_run=dry_run), ...)
```

離線驗證做法（不連任何正式服務）：用 `websockets.serve` 在 `127.0.0.1` 起一個本地假 server（固定回放事件序列，例如 `response.done` + 一筆 function call），再注入 fake executor（記錄呼叫參數、回傳樣本字串），即可離線覆蓋 VS-1..VS-9 的行為：dry-run 語意、參數遮標、逾時／錯誤分類、續 turn 上限、`arguments` 型別契約都能在無網路環境下驗證。
- **工作量：** S（3–4h）

---

## 正面觀察（值得保留）

- 金鑰只進 `Authorization` header，從不 print（`:92-93`）——符合「不落 log」原則。
- 無 key 時 exit code 2 且給出可操作指引（`:47-59`）。
- 事件型別過濾清單集中一處（`:136-140`），可讀性尚可。
