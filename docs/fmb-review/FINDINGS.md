# 逐檔審查結果（fugu-max pass）

嚴重度：🔴 高（應在下一版前修）｜🟠 中（應排入近期）｜🟡 低（整潔批次）。
行號為依提供內容推算的約略位置，均附函式/區段錨點以便定位。

---

## src/desktop_harness/daemon.py

### D1 🔴 exec 無逾時且單執行緒 — 一個卡住的腳本可永久挾持 daemon
**位置：** `daemon.py:~130–180`（`serve()` 的 `while True` accept → `op == "exec"` 區段）

`serve()` 逐連線序列處理；`exec` 在 daemon 主執行緒上直接執行任意程式碼，**沒有任何逾時**。一段含 `time.sleep(1e9)` 或無窮迴圈的 agent 腳本會讓 daemon 永久卡死：後續所有請求排隊逾時，CLI 每次退回冷啟動（或先付 `is_running()` 的 0.4s ping，見 D3）。這是本檔最實際的可用性/阻斷風險。

**建議修法（保守：per-connection thread + 軟逾時看門狗）：**

```python
import threading

def serve() -> None:
    # ...（bind / token / listen 同前）...
    while True:
        conn, _ = srv.accept()
        threading.Thread(
            target=_handle_conn, args=(conn, token, ns), daemon=True
        ).start()

def _handle_conn(conn, token: str, ns: dict) -> None:
    with conn:
        # ...讀請求 + 驗 token 同前...
        if op == "exec":
            result = {}
            done = threading.Event()

            def _run():
                result.update(_do_exec(code, ns))
                done.set()

            threading.Thread(target=_run, daemon=True).start()
            if not done.wait(timeout=float(os.environ.get("DH_EXEC_TIMEOUT", "30"))):
                resp = {"ok": False, "stderr": "exec timed out (thread leaked)"}
            else:
                resp = result
            conn.sendall((json.dumps(resp) + "\n").encode())
```

注意：Python thread 無法強制終止，逾時後該 thread 仍洩漏 — 需在文件明講；若要硬逾時，改為 exec 走子程序（成本較高，屬 BOB 決策，見 TOP10 #1）。

### D2 🟠 單實例檢查 TOCTOU — 活著的 daemon 其 socket 可能被搶走
**位置：** `daemon.py:~93–115`（`serve()` 開頭 PID 檢查 → `SOCKET_PATH.unlink()`）

流程：PID 檔存在且 pid 活著 → `is_running()` probe；**probe 例外（例如 daemon 正忙於 D1 的長 exec、ping 逾時）會落入 `except Exception: pass`**，接著 unlink 別人正在用的 socket 再 bind。結果：兩個 daemon 同時活著，舊的孤兒化、新請求全走新 daemon，行為難以追蹤。另外 `_pid_alive` 用 `os.kill(pid, 0)`，pid 重用時會誤判。

**建議修法：把 `bind()` 本身當鎖（EADDRINUSE 即代表有殘留）：**

```python
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    srv.bind(str(SOCKET_PATH))
except OSError:
    if is_running():
        raise SystemExit("daemon already running. Use: desktop-harness daemon stop")
    # 只有確認死掉的殘留 socket 才清理後重試一次
    SOCKET_PATH.unlink()
    try:
        srv.bind(str(SOCKET_PATH))
    except OSError as e:
        raise SystemExit(f"cannot bind {SOCKET_PATH}: {e}")
```

### D3 🟠 每次呼叫都付 0.4s ping；daemon 卡死時每個 CLI 呼叫都 +400ms
**位置：** `daemon.py:~55–62`（`is_running()` 的 `timeout=0.4`）

前次審查 #10 的變體仍存在：socket 檔存在但 daemon 死/忙時，每次 `is_running()` 最多等 400ms 才回 False，且失敗後不清理 stale socket，下個呼叫再等一次。與 D1 疊加時（daemon 被長 exec 卡住）體感最差。

**建議：**

```python
def is_running() -> bool:
    if not SOCKET_PATH.exists():
        return False
    if PID_PATH.exists():
        try:
            if not _pid_alive(int(PID_PATH.read_text().strip())):
                return False   # pid 死了，別再連
        except (OSError, ValueError):
            pass
    try:
        resp = client_request({"op": "ping"}, timeout=0.1)
        return bool(resp.get("ok") and resp.get("pong"))
    except Exception:
        return False
```

（清理 stale socket 的責任交給 D2 的 bind 邏輯。）

### D4 🟡 token 比較非常數時間
**位置：** `daemon.py:~160` 附近（`if req.get("token") != token:`）

本地 socket 上實務風險低，但修法零成本：

```python
import secrets
if not secrets.compare_digest(str(req.get("token") or ""), token):
    ...
```

### D5 🟡 recv 無緩衝上限；單次 recv 可能含多行而被丟棄
**位置：** `daemon.py:~74–79`（client 端）與 `serve()` 內同名迴圈

- 迴圈「直到 buf 含 `\n`」沒有上限：惡意/失控客戶端可送無上限資料撐記憶體。
- 一次 `recv` 可能讀到「第一行 + 之後的資料」，`json.loads(buf.decode())` 只解析整段 → 含多行時直接解析失敗，多餘位元組被丟掉（協議上未定義）。

**建議：** 加上限（如 16MB）並在第一個 `\n` 處切齊：

```python
MAX_FRAME = 16 * 1024 * 1024
while b"\n" not in buf:
    if len(buf) > MAX_FRAME:
        raise RuntimeError("frame too large")
    ...
line, _, rest = buf.partition(b"\n")   # 只處理 line，rest 目前丟棄但明確化
```

### D6 🟡 exec 共享可變 namespace；agent_helpers 編輯需重啟
**位置：** `daemon.py:~120` 附近（`ns = namespace()` 一次建立）與 exec 區段

跨請求共用同一 `ns` dict：使用者程式碼可覆寫 helper、留下全域狀態污染下一個請求（難 replay 的 bug 來源）。且 `agent-workspace/agent_helpers.py` 修改後 daemon 不會重載（前次 #16 仍未修）。
**建議（保守）：** 至少在 daemon docstring / README 註明「daemon 生命週期內 namespace 共享、改 agent_helpers 需 `daemon stop && start`」；更好的做法是加 `op: "reload"` 重建 `ns`。

---

## src/desktop_harness/capture.py

### C1 🟠 `window_id` 直擊敏感 app 的截圖未做敏感檢查
**位置：** `capture.py:~46–56`（`screenshot()` 開頭的 gate）

現行 gate：`app` 有給 → 只檢查**呼叫端傳入的字串**；`app` 沒給 → 只檢查 **frontmost**。若 agent 以 `screenshot(window_id=<1Password 視窗 id>)` 呼叫（該 app 非前景），**完全無敏感阻擋** — 與 SECURITY.md 宣稱的行為有落差。

**建議：** 由 `window_id` 反查 owner 後套用同一個 gate：

```python
if wid is not None and app is None:
    for w in winmod.list_windows():
        if w["id"] == wid:
            _safety.check_app_allowed(w["app"], "")
            break
```

### C2 🟠 全螢幕截圖只擋「frontmost 敏感 app」— 可見但非前景的密碼管理器仍入鏡
**位置：** `capture.py:~50–56`（`else: _safety.check_frontmost_allowed()`）+ main display 分支

`check_frontmost_allowed()` 只看前景 app；敏感視窗在第二螢幕/背景可見時，全螢幕截圖照樣洩出內容。SECURITY.md 已部分揭露此風險等級，但實作與文件的「screenshots while password-manager-like apps are targeted or frontmost」相比仍偏寬。
**建議（保守選項，擇一，屬決策點）：** (a) 全螢幕模式下掃 `list_windows()`，任何 on-screen 視窗 owner 命中敏感清單即拒絕；(b) 維持現況但把 SECURITY.md 的措辭降為精確描述（「僅阻擋前景/具名目標」）。

### C3 🟡 PNG 編碼用魔術數字 `4`
**位置：** `capture.py:~28`（`representationUsingType_properties_(4, None)`）

```python
from AppKit import NSBitmapImageFileTypePNG
data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
```

### C4 🟡 import 副作用：`TMP.mkdir(exist_ok=True)` 在模組層
**位置：** `capture.py:~19–21`

import 時建目錄，失敗會讓整個 package import 炸掉（連 `--doctor` 都跑不動）。移進 `screenshot()` 內 lazy 建立。

### C5 🟡 `window_info` 疑似死碼且比對口徑與 `screenshot` 不一致
**位置：** `capture.py:~118` 之後（`window_info()`）

提供的檔案內未見呼叫者；且它只比對 `app` 子字串、不含 title（`screenshot` 的視窗比對含 title）。若保留請統一口徑並加註用途，否則移除。

---

## src/desktop_harness/safety.py

### S1 🟠 `check_frontmost_allowed` fail-open — gate 查詢失敗時突變放行
**位置：** `safety.py:~63–77`（`except Exception: return`）

`windows.frontmost_app()` 拋任何例外（AX 權限抖動、pyobjc 錯誤）時，mutation gate 直接放行。可用性上合理（避免 AX 暫時失靈就把 agent 卡死），但這是安全邊界上的靜默降級，至少要留下痕跡：

```python
    except Exception as e:
        audit("gate_error", {"gate": "frontmost", "error": repr(e)})
        return
```

fail-open vs fail-closed 屬 BOB 決策（fail-closed 建議做成 `DH_STRICT_GATE=1` opt-in，不要直接改預設）。

### S2 🟠 `check_helper_allowed` 仍是死碼
**位置：** `safety.py:~79–87`

整個 package 內（本次可見檔案）沒有任何呼叫者；docstring 自承「keep hook for future」，但 README/SECURITY 對 safe mode 的描述會讓讀者以為有 runtime 攔截。**建議：** 移除函式，或把它真正接到 `helpers.namespace()`（組 namespace 時過濾黑名單名稱），二選一，不要留半套。

### S3 🟡 敏感名稱子字串 `"secrets"/"wallet"/"bank"` 過廣
**位置：** `safety.py:~20–23`（`_SENSITIVE_NAME_SUBSTR`）

會誤擋名稱含這些字的無辜 app（前次 #19 仍在）。保守修法：名稱比對限 **word-boundary 精確 token**，bundle id 維持子字串（bundle id 命名空間可控）：

```python
import re
_SENSITIVE_NAME_EXACT = {
    "1password", "bitwarden", "keychain access", "lastpass", "keepassxc",
    "dashlane", "nordpass", "enpass", "secrets", "wallet", "banking",
}
def _name_sensitive(name: str) -> bool:
    low = (name or "").strip().lower()
    return low in _SENSITIVE_NAME_EXACT or bool(
        re.search(r"(?i)\b(1password|bitwarden|keychain|lastpass|keepass|"
                  r"dashlane|nordpass|enpass)\b", low))
```

### S4 🟡 audit 無輪替、無大小上限；失敗全靜默
**位置：** `safety.py:~89–98`

長跑 agent 會把 `audit.jsonl` 養到無限大；寫入失敗被吞掉連一次警告都沒有。建議：超過如 5MB 時輪替為 `audit.jsonl.1`；`except` 內至少 `sys.stderr` 警告一次（用模組級 flag 防刷屏）。

---

## src/desktop_harness/windows.py

### W1 🟡 `find_app(True)` 會被當成 pid=1
**位置：** `windows.py:~62`（`if isinstance(name_or_bundle, int):`）

`bool` 是 `int` 子類。修法一行：

```python
if isinstance(name_or_bundle, bool):
    return None
```

### W2 🟡 `activateWithOptions_(1 << 1)` 魔術數字
**位置：** `windows.py:~150` 附近（兩處）

```python
from AppKit import NSApplicationActivateIgnoringOtherApps
apps[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
```

### W3 🟡 activate 輪詢迴圈重複全量列舉 NSWorkspace
**位置：** `windows.py:~130–160`（冷啟動 poll 4s/0.08s + 確認迴圈 1.2s/0.08s）

每圈 `find_app()` → `list_apps()` 全量列舉，最壞 ~60 次。輪詢「是否已 active」可直接用已到手的 pid：

```python
app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
while time.time() < deadline and not (app and app.isActive()):
    ...
```

---

## src/desktop_harness/admin.py

### A1 🟡 doctor 截圖寫死固定暫存檔
**位置：** `admin.py:~48–53`（`tempfile.gettempdir() / "dh-doctor.png"`）

`capture.screenshot` 已改唯一檔名，doctor 沒跟進；兩個終端同時跑 doctor 會互蓋（低風險，但一行就修）：

```python
path = cap.screenshot()   # 讓 capture 自己產唯一路徑
```

### A2 🟡 「AX snapshot」以 `len(nodes) > 0` 判準會誤判權限正常者 FAIL
**位置：** `admin.py:~60–68`

前次 #21 把 `>= 0` 改 `> 0` 修正了恆真問題，但反面向：前景 app 是 AX 稀疏的 app（Electron、某些終端機）時，權限完全正常仍會 FAIL，誤導排障方向。建議空節點時輸出 `WARN` 而非 `FAIL`（例如另立 `check(name, ok, ...)` 的 warn 變體或 detail 提示「前景 app 可能 AX 稀疏，請以 demo 驗證」）。

---

## src/desktop_harness/selftest.py

### T1 🟠 daemon 測項失敗時 daemon 留在背景
**位置：** `selftest.py:~150–175`（`_daemon_roundtrip`）

`quit` 在函式尾端；中途 assert 失敗（或 `exec_via_daemon` 例外）會留下背景 daemon。改成 try/finally：

```python
started = False
try:
    subprocess.check_call([... "daemon", "start", "--bg"])
    started = d.is_running()
    assert started, "daemon not running after --bg"
    resp = d.exec_via_daemon("print(1+1)")
    assert resp.get("ok") and "2" in (resp.get("stdout") or "")
finally:
    if started:
        try:
            d.client_request({"op": "quit"}, timeout=2)
        except Exception:
            pass
```

### T2 🟡 「non-destructive」敘述與實況有落差
**位置：** `selftest.py:~110–145`（`_textedit` 開新文件 + 打字 + "left open"）

會建立未存檔的 TextEdit 文件並留在畫面上。不算破壞，但 README 的「non-destructive」宜加一句「會開啟 TextEdit 並留下未存檔文件」。

### T3 🟠（可測試性，跨檔）整個 repo 沒有任何 hermetic 測試
**位置：** 專案層級 — 無 `tests/`、`pyproject.toml` 無 `[project.optional-dependencies]`/pytest 設定

`selftest` 需要真實 GUI、Accessibility/Screen Recording 權限、TextEdit 與 daemon，無法進 CI、無法在無頭環境驗譗。`safety._looks_sensitive`、`windows.find_app` 排序、`daemon` 協定（以 tmp socket + monkeypatch `SOCKET_PATH/TOKEN_PATH`）、`voice_tools.execute` 的 dry-run 分支、`capture` 的路徑唯一性，全都是**純邏輯、現在不測很可惜**的部分。詳見 TOP10 #4。

---

## src/desktop_harness/demo.py

### DM1 🟡 固定 sleep（0.4 / 0.35 / 0.6）靠運氣
**位置：** `demo.py:~20、~24、~37`

慢機器上 `cmd+n` 後 0.35s 可能還沒開好文件就打字。理想解是 `wait_for` 類輪詢 helper（前次審查 capability gap，`helpers.py` 內容未提供無法確認是否已有）。保守修法：sleep 拉長或在 demo 註明「慢機器可能掉字」。

### DM2 🟡 取第一個 TextEdit 視窗 `wins[0]`
**位置：** `demo.py:~27–33`

多份文件開啟時可能把滑鼠移進非預期視窗。取 title 含 "Untitled" 者優先即可。

---

## src/desktop_harness/voice_tools.py / scripts/voice_session.py

### V1 🟠 `--dry-run`（無 key 路徑）仍以 `dry_run=False` 實際執行工具
**位置：** `scripts/voice_session.py:~66–76`（`out = execute(name, args_, dry_run=False)`）

註解寫「list_apps is read-only ok」，但 demo 清單還含 `mouse_pos` / `screen_labels` — 與 `--dry-run` 的字面承諾矛盾（前次 #22 仍未修），且 `mouse_pos` 需要 Accessibility 權限，無權限環境會炸。修法：demo 一律 `dry_run=True`。

### V2 🟠 無最大 tool 輪數上限 — 可能無限工具迴圈
**位置：** `scripts/voice_session.py:~150–165`（`response.done` → `pending_calls` → 再 `response.create`）

模型連續產生 function call 時，session 會一直續 turn：計費持續、滑鼠持續被驅動，沒有保險絲。

```python
MAX_TURNS = 12
turns = 0
...
elif et == "response.done":
    if pending_calls:
        turns += 1
        if turns >= MAX_TURNS:
            print(f"\n[abort] exceeded {MAX_TURNS} tool turns")
            break
        await ws.send(json.dumps({"type": "response.create"}))
        pending_calls.clear()
```

### V3 🟡 VOICE.md 工具表列有 `screenshot_app`，`TOOL_DEFINITIONS` 沒有
**位置：** `VOICE.md`（tool surface 表）vs `voice_tools.py:~20–135`

文件/程式漂移；補工具或在 VOICE.md 標記「planned」。

### V4 🟡 `session.update` 傳 `"turn_detection": None`
**位置：** `scripts/voice_session.py:~96–105`

文字模式應「省略鍵」而非傳 null — 依 Realtime 類 API 慣例 null 可能被拒或視為未設。修法：組 dict 後 `if not text: session["turn_detection"] = {...}`。

### V5 🟡 重複的 `import websockets` 檢查；執行端無 consent gate 機制
**位置：** `scripts/voice_session.py:~55 與 ~85`；`voice_tools.py:execute()`

`main()` 與 `run_session()` 各檢查一次。另 `click_xy` / `move_mouse` 等執行端只有 `SESSION_INSTRUCTIONS` 的文字規則，沒有任何 confirm 機制 — 至少文件寫明「語音端 consent 僅為 prompt 層，非 runtime 強制」。

---

## 包裝 / 文件 / 腳本

### P1 🔴 SKILL.md 雙份漂移 + 打包路徑衝突
**位置：** 根目錄 `SKILL.md` vs `src/desktop_harness/data/SKILL.md`；`pyproject.toml:~22–23`

- 兩份內容已分歧：根目錄版有 **「Verify, don't assume」強制段** 與 presence 檢查規則；`data/SKILL.md` **沒有**。若 `desktop-harness skill` 輸出 data 版，裝進 `~/.grok/skills/` 的 skill 會缺少整個專案最強調的閉環紀律（SKILL.md 自己稱之為 mandatory）。
- `pyproject.toml` 同時 (a) 打包 `src/desktop_harness`（含 `data/SKILL.md`）與 (b) `force-include` 把**根目錄** `SKILL.md` 蓋到同一目標 `desktop_harness/data/SKILL.md` — 兩個來源寫同一目的地，hatch 行為是覆蓋或報錯取決版本，wheel 內容不可預期。

**建議：** 單一來源 — 以根目錄 `SKILL.md` 為準，`data/SKILL.md` 改為 build 步驟產物（或讓 `skill` 命令讀 `importlib.resources` 且 CI/build 時同步兩份並 diff 檢查）。

### P2 🟠 對外 URL 與實際 repo 不一致
**位置：** `README.md`（clone `xfreeze2/desktop-harness`）、`install.md`、`RELEASE.md`（push 目標同）、`LICENSE`（著作人 xfreeze2/freeze）

本 repo 為 `YourheroBOB/desktop-harness`。外部使用者照文件 clone 會 404 或拿到別人的 repo；RELEASE checklist 的 push 目標也不對。屬 BOB 決策（正式對外 repo 是哪個、LICENSE 名義），文件面先統一即可。

### P3 🟡 RELEASE.md 標題停在 v0.4
**位置：** `RELEASE.md:~1`；現行版本 0.4.2。

### P4 🟡 `.gitignore` 的 `*.png` 過廣
**位置：** `.gitignore`

未來文件配圖/測試 fixture PNG 會被靜默忽略。收斂為 `screenshots/`、`/tmp` 類明確路徑或 `capture-*.png`。

### P5 🟡 install.sh 缺環境守門；skill 註冊失敗會中斷安裝
**位置：** `install.sh`

- 無 macOS / Python ≥3.10 檢查（非 mac 上 `python3 -m venv` 後續全炸，訊息不友善）。
- `set -euo pipefail` 下，`$ROOT/.venv/bin/desktop-harness skill > ...` 若失敗（如權限未授）會中止整個安裝，doctor 反而有 `|| true`。建議 skill 步驟加 `|| echo "warn: skill registration failed"`。

### P6 🟡 `desktop-harness` launcher 回退 system python3 時缺 pyobjc
**位置：** `desktop-harness`（repo 根 launcher）

`.venv` 不存在時用系統 `python3`，多半沒裝 pyobjc → 使用者看到的是 import traceback 而非「請先跑 install.sh」。加一段偵測與提示即可。

### P7 🟡 observe-demo.sh 對使用者指定目錄 `rm -f "$OUT"/*.png`
**位置：** `scripts/observe-demo.sh:~10`

`OUT` 是第一個參數；使用者傳錯目錄會刪掉該目錄所有 png。保守修法：只在 `$OUT` 位於 `/tmp` 或預設路徑時才清空，或改存到 `"$OUT/frame-*.png"` 前綴刪除。

---

## 未提供內容之檔案（間接風險清單，待補審）

| 檔案 | 無法複驗的前次審查項 / 間接疑點 |
|------|--------------------------------|
| `helpers.py` | click/type/hotkey 是否都接 `check_frontmost_allowed`；`click_text(app=<pid>)` crash 是否已修；audit 是否涵蓋所有 mutation；`ensure_media_playing` 的多次 AX walk |
| `ax.py` | `_ax_point` 是否改用 `kAXValueCGPointType` 常數；walk 過濾邏輯；snapshot cache |
| `input.py` | `_KEYCODES` 覆蓋（`cmd+.`、F-keys）；click settle sleeps；`type_text` 8ms/char |
| `presence.py` | main-thread AppKit 規則與 `keep_alive`（OBSERVE-LOOP.md 描述的歷史 bug 區） |
| `run.py` | `_want_daemon`/自動路由；`skill` 命令讀哪份 SKILL.md（P1 的關鍵變數）；`agent-workspace` 預設路徑 |
