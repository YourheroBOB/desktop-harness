# Findings — 逾時、重試與錯誤恢復（`voice_session.py`、`safety.py`、`selftest.py`、`demo.py`）

---

## TR-1（P1）`voice_session.py`：WS 連線無 `open_timeout`、事件迴圈無 idle timeout、無重試退避

**位置：** `scripts/voice_session.py` — `run_session()`：
- `websockets.connect(WS_URL, additional_headers=headers, max_size=8*1024*1024)` — 未指定 `open_timeout`／`ping_interval`／`close_timeout`。
- `async for raw in ws:` — 無整體／idle 逾時；伺服器停止送事件時無限等待。
- 連線失敗／中斷後直接結束，無任何重試或退避。

**影響：**
- 網路或 API 端異常時，腳本可能**永遠掛住**（佔著麥克風與行程）或安靜地結束而使用者不知道為什麼。
- 一次瞬斷就終止整個 voice session，對「hotkey 啟動的常駐語音控制」產品形態（VOICE.md 規劃）是基本可用性缺口。
- `--text` 模式靠 `response.done` + `break` 結束，若模型不產生 `response.done`（錯誤、tool call 循環）會無限等待。

**建議修法：**
```python
async with websockets.connect(
    WS_URL,
    additional_headers=headers,
    max_size=8 * 1024 * 1024,
    open_timeout=15,          # 連線階段上限
    ping_interval=20,         # keepalive：偵測半開連線
    ping_timeout=10,
    close_timeout=5,
) as ws:
    ...
    async for raw in ws:      # 包一層整體上限：
```
- `--text` 模式加 `asyncio.wait_for(run_text_turn(ws, text), timeout=90)`。
- 頂層加有限重試（例如 3 次、exponential backoff 1s/2s/4s，只對連線類錯誤），重試前印出清楚訊息。
- 驗證一律可在**不連線**下測：對本機假 WS server（`websockets.serve` 於 `localhost` 臨時 port，測試碼內自起自停）或 mock `websockets.connect` 測逾時與重試路徑。**測試不得連 `api.x.ai`。**

**驗證方式：** 本機假 server（127.0.0.1 + 隨機 port，測試自建）：(a) server 接受連線後不回應 → 斷言 15s 內拋逾時而非永掛；(b) server 拒絕連線 → 斷言 3 次重試後帶錯誤退出，backoff 間隔如預期。假 key 用 `FAKE_VALUE_FOR_TEST`。

**優先級：** P1

---

## TR-2（P1）voice tool `execute()` 同步阻塞在 asyncio 事件迴圈

**位置：** `scripts/voice_session.py` — `response.function_call_arguments.done` 分支：`result = execute(name, arguments, dry_run=dry_run)` 為**同步呼叫**，直接在 `async for` 迴圈內執行。

**影響：**
- `execute` 內的 helper 可能跑數百 ms 到數秒（`move_to(duration=0.4)`、`open_app` 冷啟動 4s 輪詢、截圖）。期間事件迴圈完全阻塞：收不到後續 WS 事件、keepalive ping 送不出去 → **伺服器端可能因 ping 超時把整個 session 斷線**。
- 這會把 TR-1 的修法（ping keepalive）直接打穿：加了 keepalive 反而更容易在長動作中被斷線。

**建議修法：**
```python
result = await asyncio.to_thread(execute, name, arguments, dry_run=dry_run)
```
- 注意：`execute` 內呼叫的 helper 含 AppKit／HID 操作。與 daemon 情境同理（OBSERVE-LOOP 的 SIGABRT 教訓），**需先確認** `to_thread`（背景 thread）執行這些 helper 是否安全 —— presence overlay 的約束是「main thread」，但 `voice_session.py` 本身沒有 AppKit run loop，`execute` 走的是 helpers 的 AX／Quartz 路徑（`presence` 會在內部處理 main-thread 問題，`keep_alive` 分塊方案即為此設計）。**保守做法：先用 `to_thread` 包住，並對含 presence 的 tool 加註需要實測（按 OBSERVE-LOOP 的多幀驗證法）。**

**驗證方式：** 本機假 WS server 送一個假的 function call 事件 → fake `execute`（monkeypatch 為 `time.sleep(2)`）→ 斷言期間事件迴圈仍能處理並發送達的其他事件（例如同時再送一個 delta 事件，斷言 2 秒內被印出）。無網路、無真實 GUI 動作。

**優先級：** P1

---

## TR-3（P2）`response.done` + `pending_calls` 自動續 turn 無上限

**位置：** `scripts/voice_session.py` — `response.done` 分支：只要有 pending tool calls 就再送一次 `response.create`，`pending_calls.clear()`。註解自己承認 "simplified"。

**影響：** 模型若持續產生 tool calls（例如 `screen_labels` 找不到目標就一直重試 —— SESSION_INSTRUCTIONS 裡恰好寫了 "If a control is missing, call screen_labels and try again"），此迴圈**無終止條件**：無限 API 消耗（voice 按分鐘計費）+ 無限桌面操作。

**建議修法：**
```python
MAX_AUTO_TURNS = 8
auto_turns = 0
...
elif et == "response.done":
    if pending_calls and auto_turns < MAX_AUTO_TURNS:
        auto_turns += 1
        await ws.send(json.dumps({"type": "response.create"}))
        pending_calls.clear()
    elif pending_calls:
        print(f"stopping: {MAX_AUTO_TURNS} consecutive tool turns")
        break
```
並在每次自動續 turn 印出計數（可觀測性）。

**驗證方式：** mock/假 server 連續送「function call → response.done」事件循環 20 次 → 斷言 client 在第 8 次後停止並印出訊息。

**優先級：** P2（voice 路徑目前是 experimental，若升級為產品線則升 P1）

---

## TR-4（P1）`safety.audit()` 靜默吞掉所有例外；audit log 無輪替

**位置：** `safety.py` — `audit()` 的 `except Exception: pass`；`_AUDIT` 為 append-only JSONL，無輪替、無保留政策。

**影響：**
- **錯誤恢復／可觀測性雙重缺口**：audit 寫入失敗（磁碟滿、權限、目錄損壞）時**完全無聲** —— 安全稽核軌跡斷了也沒人知道。對一個「會動真實滑鼠鍵盤」的工具，稽核記錄靜默失效是安全相關的可靠性問題。
- 無輪替：長跑 daemon 的 audit.jsonl 無限成長（PRE-RELEASE-REVIEW #18 已指出，此處補上「靜默失敗」這半邊）。
- `_AUDIT` 路徑在 import 時固定，測試與執行期改 `DH_AUDIT_LOG` 無效（小問題，一併修）。

**建議修法：**
1. 寫入失敗不要 `pass`：至少 `sys.stderr` 一行（節流，避免磁碟滿時洗版），或在 daemon 情境回報到請求回應。
2. 輪替：超過大小上限（例如 5MB）時 rotate 成 `audit.jsonl.1`（保留 1–2 代）。輪替同樣要容錯且失敗可見。
3. 路徑改為呼叫時解析（`_audit_path()`），讓 `DH_AUDIT_LOG` 執行期可測。

```python
def audit(event, detail=None):
    path = Path(os.environ.get("DH_AUDIT_LOG",
                Path.home() / ".desktop-harness" / "audit.jsonl"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(path, max_bytes=5_000_000, keep=2)
        with path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception as e:
        _warn_once(f"audit write failed: {e}")   # stderr, 每分鐘最多一次
```

**驗證方式：** 單測（`tmp_path`）：(a) monkeypatch `Path.open` 拋 `OSError` → 斷言 stderr 出現警告且不拋例外；(b) 預寫 6MB 假檔 → 呼叫 audit → 斷言 rotate 出現且行數保留；(c) 設 `DH_AUDIT_LOG` 環境變數**於呼叫前** → 斷言寫到新路徑（修後才會過）。

**優先級：** P1

---

## TR-5（P2，待確認）helpers／input 固定 sleeps 主導多步延遲

**位置：** `helpers.py`／`input.py`（本次未審；行為引自 PRE-RELEASE-REVIEW #13：click settle 0.04+0.02、`wait_stable` 預設 0.2、`activate` 0.12/0.35、`click_text` 必接 `wait_stable`）。

**影響：** 每個動作的固定 sleep 疊加，是 agent 多步任務延遲的基底成本；尤其 daemon 路徑下 `wait_stable` 0.2s × N 步。

**建議修法（方向，待審碼後具體化）：** 優先以 AX 狀態變化（element enabled／value changed／window list 變動）作為等待條件，固定 sleep 只留給 HID settle 的最小值；`wait_stable` 預設在 daemon 路徑降為 0.05–0.1s。

**驗證方式：** 待實作後以 selftest 現有的每項 ms 印出做前後對照（`desktop-harness selftest` 輸出已含耗時）。

**優先級：** P2（未審碼前不給更高）

---

## TR-6（P2）`selftest` daemon roundtrip 改變使用者全域狀態

**位置：** `selftest.py` — `_daemon_roundtrip()`：先對**使用者現有 daemon** 送 `quit`，再以 `--bg` 起一個新的，測完再 quit。整個過程對使用者環境有真實副作用。

**影響：**
- 使用者跑 `selftest`（README 明示為 release check 的標準動作）後，原本暖著的 daemon 被殺掉、最後也沒還原 → 下一次 agent 任務回到冷啟動，使用者無感地變慢。
- 測試隔離性原則上應避免動被測系統外的全域狀態。

**建議修法：** 讓 selftest 的 daemon 測試**全程使用沙箱路徑**：
```python
env = {**os.environ,
       "DH_SOCKET": str(tmp / "selftest.sock"),
       "DH_TOKEN_PATH": str(tmp / "selftest.token")}
subprocess.check_call([sys.executable, "-m", "desktop_harness.run",
                       "daemon", "start", "--bg"], env=env)
```
（daemon 已支援 `DH_SOCKET`／`DH_TOKEN_PATH`，改動集中在 selftest。）若要保留「真實路徑 roundtrip」的涵蓋，另外標注為選配項並在測前記錄／測後還原 `daemon status`。

**驗證方式：** 跑 `selftest` 前後各執行 `daemon status` → 修後使用者的 daemon 狀態不變；沙箱 socket 於測後不存在。使用 `tempfile.TemporaryDirectory()`，不寫 repo。

**優先級：** P2

---

## 其他（P2，順手項）

- **`demo.py` 固定 sleeps**（0.4 / 0.35 / 0.6）：demo 是給人看的 smoke test，固定 sleep 可接受；唯 `open_app` 後 0.4s 若 app 已開會白等 —— `activate` 已有 frontmost skip，此處影響極小，僅記錄不強制修。
- **`scripts/observe-demo.sh`**：`rm -f "$OUT"/*.png` 開場清理 + 輸出到指定目錄，行為正確；`screencapture` 子進程 `|| true` 容錯 OK。24 幀 × 數 MB 的輸出目錄若重複跑會累積 —— 開場 `rm` 已緩解，無需動。
