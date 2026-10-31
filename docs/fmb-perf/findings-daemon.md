# Findings — daemon（`src/desktop_harness/daemon.py`）

daemon 是產品的「暖啟動」核心：單一 Unix socket、NDJSON 協議、token 認證。以下是併發、競態、逾時與錯誤恢復方面的發現。

---

## DAEMON-1（P0）單執行緒 accept 迴圈 + 無連線逾時 → 一個掛住的 client 讓整個 daemon 無回應

**位置：** `daemon.serve()` — `while True: conn, _ = srv.accept()` 之後直接在主執行緒同步處理該連線（`conn.recv(...)` 迴圈無 `settimeout`）。

**影響：**
- 任何 client（同一 UID 下的任意行程）只要 `connect()` 後**不送資料**，`conn.recv()` 就會無限阻塞。
- daemon 是單執行緒 → 這一個連線會讓**所有後續 agent 步驟**（ping、exec）全部卡死，直到該 client 斷線。
- 對長跑 agent 任務是整體失效等級的可靠性問題：一個寫錯的腳本（例如 connect 後 crash 在 send 之前）就能讓 daemon 進入假死。

**建議修法（保守版，優先）：**
1. `accept()` 後立即 `conn.settimeout(5.0)`（請求讀取階段）— 掛住的 client 5 秒後被丟棄，daemon 恢復服務。
2. 保持 exec 序列化（見下方注意事項），只對「讀請求」與「寫回應」加逾時。

```python
conn, _ = srv.accept()
with conn:
    conn.settimeout(5.0)          # 讀請求階段逾時
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(1 << 20)
        ...
```

**注意（重要決策點）：** 不要直接改成 thread-per-connection 跑 exec。`docs/OBSERVE-LOOP.md` 已確認 **AppKit 在非主執行緒呼叫 window 方法會讓整個進程 SIGABRT**（無 Python 例外、不可恢復），而 daemon exec 的腳本可能呼叫 presence／AppKit 相關 helper。因此：

- **保守修法**：單執行緒 + 每連線讀取逾時 + 例外隔離（DAEMON-2）。這已解決「假死」問題。
- **進階修法（另行評估）**：per-connection 讀取線程 + 單一 exec 工作序列（一個 queue + 一個 worker thread），exec 統一在 worker thread 序列化執行。需先確認 worker thread 執行 AppKit 呼叫是否也觸發 SIGABRT —— AppKit 大多要求 **main thread**，不是「同一條 thread」即可，故保守版為預設建議。

**驗證方式（本機、無網路）：**
```python
# 測試沙箱：DH_SOCKET=<tmp>/t.sock DH_TOKEN_PATH=<tmp>/t.token
# 1) 啟動 daemon（子進程）
# 2) client A: connect 後 sleep，不送資料
# 3) client B: 送 {"op":"ping","token":...}
# 修前：client B 永久阻塞（或直到 client A 斷線）
# 修後：client B 應在 ~5 秒內收到 pong，daemon 存活
```
另以 `--dry-run` 之外不需任何網路；全程用 `tempfile.TemporaryDirectory()`。

**優先級：** **P0**

---

## DAEMON-2（P0）連線處理中未捕捉的 socket 例外會終結整個 daemon

**位置：** `daemon.serve()` 的連線處理區段 — 只有 `json.JSONDecodeError` 被 catch；`conn.sendall(...)` 若拋出 `BrokenPipeError`／`ConnectionResetError`（client 在 server 回寫前斷線），例外會傳出 `while True` 迴圈，執行 `finally`（關 server、刪 socket/pid）後 **daemon 整個結束**。

**影響：**
- 一次 client 端的早退（agent 腳本 crash、timeout 後 client 關閉 socket）就可能殺死 daemon。
- 之後所有 CLI 呼叫退回冷啟動路徑（每次重新 import pyobjc），多步任務效能直接退化 — 這正是 daemon 存在要避免的成本。
- 屬「單一事件 → 服務永久失效」，與 DAEMON-1 同級。

**建議修法：** 把每個連線的處理包進獨立的 try/except，任何 `OSError` 都只關掉該連線、記一筆日誌（見 OBS-1），迴圈繼續：

```python
while True:
    try:
        conn, _ = srv.accept()
    except OSError:
        break
    try:
        _handle_conn(conn, token, ns)      # 現有邏輯搬進來
    except Exception:
        traceback.print_exc()              # 或結構化日誌
    finally:
        conn.close()
```

**驗證方式：**
```python
# 沙箱 daemon 起來後：
# client 送 {"op":"ping","token":...}，讀到 pong 前（或讀到後）立刻 close()
# 再用第二個 client ping — 修前 daemon 已死（is_running() == False），
# 修後 daemon 存活且持續回應。重複 20 次確認穩定。
```

**優先級：** **P0**（與 DAEMON-1 建議同一個 PR 一起修）

---

## DAEMON-3（P1）`exec` 無伺服器端逾時 — client 超時後 daemon 仍被佔死

**位置：** `daemon.serve()` 的 `op == "exec"` 分支；`exec_via_daemon(code, timeout=60.0)` 的 timeout 只作用在 **client 端** socket。

**影響：**
- 一段含 `time.sleep(600)` 或無限迴圈的腳本會讓 daemon 卡 10 分鐘；client 60 秒後逾時放棄，但 daemon 仍被佔住，後續所有 agent 步驟全部逾時失敗。
- agent 重試只會堆積更多逾時，無法自癒，只能手動 `daemon stop`（而 stop 的 `quit` op 也進不了被佔住的迴圈 → 只能殺進程）。

**建議修法：**
1. 協議層：請求可帶 `"timeout"` 欄位（上限如 120s），server 據此設定防護。
2. 執行層（保守）：在 exec 前 `signal.setitimer(signal.ITIMER_REAL, timeout)`、`signal.signal(SIGALRM, raise TimeoutError)`，except 後回 `{"ok":false,"error":"exec timeout"}`。daemon 是單執行緒主 thread，`signal` 可用；但 exec 內的 C 呼叫（pyobjc）可能延遲 delivery —— 文件上要註明「best effort」。
3. 最保守的替代：至少在文件／SKILL 註明「無 server 端逾時，腳本請自帶 `wait()` 上限」，並提供 `daemon stop --force`（kill PID）作為恢復手段。
4. 新增 `op: "interrupt"`（清空佇列／設 interrupt flag）可以之後再評估，先不擋這個 PR。

**驗證方式：** 沙箱 daemon，`exec_via_daemon("import time; time.sleep(30)", timeout=3)` → 修前：3 秒後 client 逾時、daemon 再卡 27 秒（期間 ping 無回應）；修後：daemon 在 ~timeout 時回錯誤並立即恢復 ping。

**優先級：** P1

---

## DAEMON-4（P1）`is_running()` 0.4s ping：daemon 掛掉時每次 CLI 呼叫多付 400ms

**位置：** `daemon.is_running()`（`client_request({"op":"ping"}, timeout=0.4)`）；呼叫方為 CLI 的 daemon 路由決策（`run.py` 未審，行為見 PRE-RELEASE-REVIEW #10 —— 該 review 建議 50–100ms，目前程式碼仍為 0.4s）。

**影響：**
- socket 檔存在但 daemon 已死／卡住的常見情境（crash、DAEMON-2、DAEMON-1）下，**每一次** `desktop-harness` 呼叫都先白等 400ms 才退回 in-process —— 對「多步任務每步都是一次 CLI 呼叫」的使用模式，等於每步 +0.4s。
- daemon 健康時也要付一次 connect+ping 往返，但這是合理成本；問題集中在 stale socket 情境。

**建議修法：**
1. ping timeout 降到 **0.1s**（本機 Unix socket，健康 daemon 的 pong 遠低於此）。
2. connect 失敗／逾時時，若 PID 檔存在且該 PID 已死 → 主動 `unlink` socket 與 pid 檔（自癒，之後的呼叫直接走 in-process，不再重複探測失敗）。
3. 可選：connect 前先讀 PID 檔做 liveness check（`_pid_alive` 已有現成函式），活著才嘗試 ping。

**驗證方式：** 在 `tmp_path` 建假的 `daemon.sock`（touch 空檔）+ 不存在的 PID → `is_running()` 應在 ≤0.15s 內回 False，且（若實作自癒）第二次呼叫為即時。用 `time.perf_counter()` 斷言。全程沙箱路徑，不影響使用者真實 daemon。

**優先級：** P1

---

## DAEMON-5（P2）`daemon start` 單例檢查為 TOCTOU，並發 start 可產生雙實例

**位置：** `daemon.serve()` 開頭：讀 PID 檔 → 探測 → `unlink` 舊 socket → `bind`。兩個並發 `daemon start` 都可能通過檢查，各自 bind（後 bind 者拿到路徑、先 bind 者的 socket 被 unlink 後成為孤兹），行為未定義。

**影響：** 低機率（人為手動雙擊啟動、script 競態），但一旦發生：兩個 daemon 各持有不同 token（`_write_token` 覆寫），client 讀到的 token 只對其中一個有效，症狀是間歇性 `unauthorized` —— 難以診斷。

**建議修法：** 用 lock file 做原子單例（`os.open(path, O_CREAT|O_EXCL)` 或 `fcntl.flock`）：
```python
lock = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
# 拿不到 → 讀 PID、探測、refuse；程序結束時 unlink lock
```
並在 `finally` 一併清理 lock 檔。

**驗證方式：** 沙箱中同時 spawn 兩個 `serve()` 子進程 → 修後恰一個成功、另一個帶清楚訊息退出；socket／token 只有一份。

**優先級：** P2

---

## DAEMON-6（P2）SIGTERM 不會執行 `finally`，留下 stale socket／PID 檔

**位置：** `daemon.serve()` 的 `try/finally`；Python 對 SIGTERM 的預設行為是直接終止，`finally` 不執行。

**影響：** `kill <pid>`／系統關機後留下 `daemon.sock` 與 `.pid`。下次 `is_running()` 付一次失敗 ping 的成本（結合 DAEMON-4 = 每次 400ms），且 `daemon status` 回報誤導性的「socket 存在」。不會造成資料損壞（下次 start 會清理），故列 P2。

**建議修法：**
```python
import signal
def _shutdown(signum, frame):
    raise SystemExit(0)          # 觸發 finally 清理
signal.signal(signal.SIGTERM, _shutdown)
```
（`SystemExit` 會跑 `finally`。）另建議把清理邏輯抽成 `_cleanup()` 供 handler 與 finally 共用，保證冪等。

**驗證方式：** 沙箱 daemon 起後 `os.kill(pid, SIGTERM)` → 等待 1 秒 → socket／pid 檔應不存在；`is_running()` 立即 False。

**優先級：** P2

---

## DAEMON-7（P2）請求 buffer 無大小上限；token 比較非 constant-time

**位置：** `serve()` 的 `buf += chunk` 迴圈（無上限）；`if req.get("token") != token`。

**影響：**
- 無上限：同 UID 行程可送無限量資料撐爆 daemon 記憶體。威脅模型有限（同 UID 本就能直接 exec），但一個誤寫的 client（例如把 binary 當 JSON 送）也可能造成大 buffer。
- 非 constant-time 比較：理論性 timing side channel，本機 Unix socket 情境下風險極低，列為衛生項目。

**建議修法：**
```python
MAX_REQ = 8 * 1024 * 1024
if len(buf) > MAX_REQ:
    conn.sendall(b'{"ok":false,"error":"request too large"}\n')
    continue
# token 比較：
import secrets
if not secrets.compare_digest(str(req.get("token") or ""), token):
```

**驗證方式：** 沙箱 daemon，client 送 > 8MB 無換行資料 → 應收到明確錯誤而非撐爆記憶體；正常請求不受影響。

**優先級：** P2
