# desktop-harness 資安與可靠性稽核報告（AUDIT）

- **日期：** 2026-08（本報告建立於目前分支）
- **範圍：** `src/desktop_harness/`（safety.py、daemon.py、windows.py、capture.py、admin.py、selftest.py、voice_tools.py、demo.py）、`scripts/voice_session.py`、`install.sh`、`pyproject.toml`、`SECURITY.md` 等可見檔案
- **方法：** 靜態程式碼審查（輸入驗證、命令注入、路徑穿越、機密外洩、相依套件、錯誤處理、併發、fail-open/fail-closed），並交叉參考 `docs/PRE-RELEASE-REVIEW.md` 的歷史發現，驗證 v0.4 是否已修復。
- **重要限制：** `src/desktop_harness/run.py`、`helpers.py`、`input.py`、`ax.py`、`presence.py` 內容未提供本次審查，無法逐行稽核；相關風險標記為「待驗證」（見 A-21）。
- **行號為約略值**（依目前分支檔案內容估算），以函式名稱為主要定位。
- 本報告不含任何真實 token、金鑰、密碼、客戶個資或訊息內容。

## 嚴重度定義

| 等級 | 定義 |
|------|------|
| **High** | 可導致桌面控制權濫用、敏感資料外洩，或核心功能（daemon）整體失效 |
| **Medium** | 防護繞過、隱私外流、可靠性明顯受損，需在下一版修復 |
| **Low** | 縱深防禦或衛生問題 |
| **Info** | 記錄性質、目前作法正確或屬設計取捨 |

## 發現總表

| ID | 嚴重度 | 主題 | 位置（約） |
|----|--------|------|-----------|
| A-01 | High | daemon 單執行緒 + exec 無 timeout → 阻塞型 DoS | `src/desktop_harness/daemon.py:127-181` |
| A-02 | High | 連線處理無例外保護 → 單一 client 可讓 daemon 整個終止 | `src/desktop_harness/daemon.py:129-181` |
| A-03 | High | 敏感 app 前景檢查 fail-open | `src/desktop_harness/safety.py:69-73` |
| A-04 | Medium | audit log 靜默失敗（fail-open） | `src/desktop_harness/safety.py:86-93` |
| A-05 | Medium | 非前景但可見的敏感視窗仍可被截圖 | `src/desktop_harness/capture.py:38-50` |
| A-06 | Medium | voice session 將 AX labels / 工具結果送往遠端 API | `scripts/voice_session.py:130-175` |
| A-07 | Medium | voice 同意規則僅存在於 prompt，runtime 無強制 | `src/desktop_harness/voice_tools.py`（`execute()`） |
| A-08 | Medium | `check_helper_allowed` 死碼；DH_* gate 可被腳本自行翻掉，文件未明說 | `src/desktop_harness/safety.py:77-84` |
| A-09 | Medium | 相依套件無版本上限／無 hash pinning | `pyproject.toml:7-11`、`install.sh:11-15` |
| A-10 | Medium | `screenshot(path=...)` 為任意路徑寫入原語 | `src/desktop_harness/capture.py:38-50` |
| A-11 | Medium | daemon 單實例檢查 TOCTOU race | `src/desktop_harness/daemon.py:89-106,119` |
| A-12 | Low | token 比較非 constant-time | `src/desktop_harness/daemon.py:146` |
| A-13 | Low | daemon 停止後 token 檔殘留 | `src/desktop_harness/daemon.py:182-187` |
| A-14 | Low | 請求讀取無大小上限（server 與 client） | `src/desktop_harness/daemon.py:131-135`、`client_request()` |
| A-15 | Low | `is_running()` 0.4s ping 逾時拖慢每次 CLI 呼叫 | `src/desktop_harness/daemon.py:51-57` |
| A-16 | Low | 截圖暫存目錄權限取決於 TMPDIR | `src/desktop_harness/capture.py:15-16` |
| A-17 | Low | sensitive 子字串（bank/wallet/secrets）過廣且僅比對名稱 | `src/desktop_harness/safety.py:20-29` |
| A-18 | Low | voice session 工具呼叫迴圈無上限 | `scripts/voice_session.py`（`run_session`） |
| A-19 | Info | `open -a` 使用 list-form subprocess，無 shell injection（正確） | `src/desktop_harness/windows.py`（`activate()`） |
| A-20 | Info | audit log 無 rotation／retention 政策 | `src/desktop_harness/safety.py:86-93` |
| A-21 | 待驗證 | 未提供檔案（run/helpers/input/ax/presence）之關鍵驗證項 | 見內文 |

---

## 詳細發現

### A-01（High）daemon 單執行緒 + exec 無 timeout → 阻塞型 DoS

- **位置：** `src/desktop_harness/daemon.py:127-181`（`serve()` 主迴圈與 `op == "exec"` 分支）
- **問題：** `serve()` 在單一執行緒中 accept → recv → `exec(...)`。任何一段 agent 腳本寫出無限迴圈（例如 `while True: pass`）會**永久**占住 daemon；期間所有其他 client（包括 `daemon stop` 的 `{"op":"quit"}`）都只能等到各自的 socket timeout（預設 60s）後失敗。`exec` 分支也沒有任何執行時間上限。
- **重現方式：**
  ```bash
  desktop-harness daemon start --bg
  desktop-harness <<'PY'
  import time
  while True:
      time.sleep(3600)
  PY
  # 另一個終端機：desktop-harness daemon status → 卡到 timeout
  ```
- **影響：** 多步驟 agent 任務中一個壞腳本即讓 daemon 進入假死；`selftest` 的 daemon roundtrip 也會被拖垮（可靠性）。
- **修補建議：**
  ```python
  # daemon.py — serve() 內：每個連線用 thread 處理，exec 加 watchdog
  import threading

  def _handle(conn, token, ns):
      try:
          # ... 現有 recv / auth / op 邏輯 ...
          if op == "exec":
              # 在子執行緒跑、主流程計時；超時則回錯誤並中斷該連線
              ...
      except Exception:
          pass  # 見 A-02：單一連線的失敗不得影響其他連線

  while True:
      conn, _ = srv.accept()
      threading.Thread(target=_handle, args=(conn, token, ns), daemon=True).start()
  ```
  另建議：exec 前 `signal.alarm` / 子執行緒 join(timeout) 超時即拒絕並回 `{"ok":false,"error":"exec timeout"}`。注意若 exec 在子執行緒，無法強制殺掉 Python 字節碼，保守做法是「超時即斷線回錯並標記該 ns 需重啟」。

---

### A-02（High）連線處理無例外保護 → 單一 client 可讓 daemon 整個終止

- **位置：** `src/desktop_harness/daemon.py:129-181`（`conn` 的 `with` 區塊）
- **問題：** `conn.recv` / `conn.sendall` 沒有包 try/except。若 client 在 server 回應前斷線，`sendall` 拋 `BrokenPipeError`，例外穿出 `while True` 迴圈 → `finally` 清掉 socket 與 PID 檔 → **整個 daemon 死掉**。一個連線異常等於全體服務下線。
- **重現方式：**
  ```bash
  desktop-harness daemon start --bg
  # 用一個連上後立刻斷線的 client：
  python3 - <<'PY'
  import socket
  s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  s.connect("<SOCKET_PATH>")   # 填實際路徑
  s.close()                    # 未送完整請求即斷線
  PY
  desktop-harness daemon status   # daemon 已死
  ```
  （另一個更容易的變體：送出 `{"op":"exec",...}` 後不等回應就斷線。）
- **影響：** 可靠性 — 任何網路/逾時異常都會讓常駐服務消失，且 agent 端只會看到 fallback 到本地執行（慢），無明顯錯誤。
- **修補建議：**
  ```python
  # daemon.py serve() 內
  while True:
      conn, _ = srv.accept()
      try:
          with conn:
              # ... 現有 recv / auth / op 處理 ...
      except (BrokenPipeError, ConnectionResetError, OSError):
          continue   # 單一連線失敗不影響 daemon 存活
  ```

---

### A-03（High）敏感 app 前景檢查 fail-open

- **位置：** `src/desktop_harness/safety.py:69-73`（`check_frontmost_allowed()`）
- **問題：**
  ```python
  try:
      from . import windows as winmod
      front = winmod.frontmost_app()
  except Exception:
      return          # ← 任何例外都直接放行
  ```
  若 `frontmost_app()` 拋例（AX 權限被撤、pyobjc 異常、視窗伺服器忙碌），所有依賴此 gate 的 mutation（點擊、輸入、截圖）會**無聲放行**——這是典型的 fail-open。資安控制失敗時應傾向拒絕。
- **重現方式：** 在 `frontmost_app()` 拋例的環境（例如暫時撤銷 Accessibility 後呼叫間歇性失敗）執行 `type_text(...)`；gate 不會擋。
- **影響：** 敏感 app（密碼管理器）正在前景時，系統不穩定瞬間的 mutation 不受保護。
- **修補建議（保守 fail-closed，可由 env 覆寫）：**
  ```python
  # safety.py
  def check_frontmost_allowed() -> None:
      if allow_sensitive():
          return
      try:
          from . import windows as winmod
          front = winmod.frontmost_app()
      except Exception as e:
          audit("frontmost_check_failed", {"error": str(e)})
          raise PermissionError(
              "could not verify frontmost app; refusing mutation "
              "(fail-closed). Set DH_ALLOW_SENSITIVE=1 to override."
          )
      if not front:
          return
      check_app_allowed(front.get("name") or "", front.get("bundle_id") or "")
  ```
  決策點：fail-closed 可能在 AX 偶發失敗時擋掉合法操作，需 BOB 決定是否接受此取捨（建議接受：寧可擋錯）。

---

### A-04（Medium）audit log 靜默失敗（fail-open）

- **位置：** `src/desktop_harness/safety.py:86-93`（`audit()`）
- **問題：** `except Exception: pass` — 磁碟滿、目錄權限錯、路徑被改（`DH_AUDIT_LOG` 可由環境變數導向 `/dev/null`）時，稽核軌跡**無聲消失**，且 mutation 照常執行。對以 audit log 作為安全承諾的產品（SECURITY.md 明列），這是 fail-open。
- **重現方式：** `DH_AUDIT_LOG=/dev/null desktop-harness <<'PY' ... mutation ... PY` → 無任何警告。
- **修補建議：** 至少對失敗發出 stderr 警告並計數；保守做法是 mutation 類事件在 audit 失敗時也 fail（或拒絕）：
  ```python
  _AUDIT_FAILED = 0

  def audit(event: str, detail=None, *, required: bool = False) -> None:
      global _AUDIT_FAILED
      try:
          ...
      except Exception as e:
          _AUDIT_FAILED += 1
          print(f"[safety] audit write failed ({_AUDIT_FAILED}x): {e}",
                file=sys.stderr)
          if required:
              raise   # 關鍵 mutation：稽核寫不進去就不要做
  ```

---

### A-05（Medium）非前景但可見的敏感視窗仍可被截圖

- **位置：** `src/desktop_harness/capture.py:38-50`（`screenshot()` 的無 app 範圍分支）
- **問題：** 無 `app` 參數時只呼叫 `check_frontmost_allowed()`。但 macOS 常見情境：密碼管理器視窗**可見但非前景**（雙螢幕、Split View、背景視窗露出），全螢幕／window_id 擷取仍會把它的內容寫進 PNG，gate 完全沒攔到。SECURITY.md 聲稱「screenshots while password-manager-like apps are targeted or frontmost」會被擋——「可見但非前景」是宣稱與實作的縫隙。
- **重現方式：** 開啟 1Password 主視窗後點回瀏覽器（1Password 視窗仍在畫面上），執行 `screenshot()`（無參數）→ PNG 含密碼管理器畫面，無 PermissionError。
- **修補建議：** 對 `list_windows()` 回傳的**所有** on-screen 視窗跑 sensitive 檢查：
  ```python
  # capture.py screenshot() 無 app 分支
  else:
      for w in winmod.list_windows():
          _safety.check_app_allowed(w["app"] or "")
      _safety.check_frontmost_allowed()
  ```
  （保守取捨：可能偶爾擋到名稱含 "bank"/"wallet" 的無關視窗——與 A-17 一併處理，改用 bundle id 判斷可大幅降低誤擋。）

---

### A-06（Medium）voice session 將 AX labels / 工具結果送往遠端 API

- **位置：** `scripts/voice_session.py:130-175`（`run_session()` 的 `function_call_output` 回送）
- **問題：** `screen_labels` 的完整結果（前景 app 的 AX 標籤——可能含訊息標題、聯絡人名稱、文件內容摘要）與 `list_apps` 結果**全文**透過 WebSocket 送到 `api.x.ai`。這是 voice 產品形態的固有設計，但：
  1. 沒有任何同意 UI 或提示告知「畫面上的文字會被送到第三方」；
  2. 結果沒有 redaction 或長度上限（stdout 有 `[:300]` 截斷，但送回 WS 的是全文）。
- **重現方式：** 前景開一個含敏感標題的視窗，執行 `voice_session.py --text "what's on screen"` → 工具結果全文出站。
- **修補建議：**
  ```python
  # voice_session.py — 送出前截斷 + 標示
  MAX_OUT = 2000
  out = result[:MAX_OUT] + ("…[truncated]" if len(result) > MAX_OUT else "")
  # 並在 session 啟動時印出明確隱私提示：
  print("note: tool results (incl. on-screen labels) are sent to the "
        "voice API provider. Use --dry-run to avoid this.")
  ```
  長期：敏感 app 前景時拒絕 `screen_labels`（沿用 `check_frontmost_allowed`）。

---

### A-07（Medium）voice 同意規則僅存在於 prompt，runtime 無強制

- **位置：** `src/desktop_harness/voice_tools.py`（`execute()` 與 `SESSION_INSTRUCTIONS`）
- **問題：** 「不得傳訊／購買／刪除」只寫在給模型的 instructions 裡，模型可無視；`execute()` 對 `click_xy`／`type_text`／`hotkey` 沒有任何 runtime deny-list 或確認 hook。語音輸入又天然容易誤觸發（誤聽、旁人說話）。
- **重現方式：** `--text "delete everything in Finder"` → 工具層不會有任何攔截，模型說做就做。
- **修補建議：** 在 executor 層加保守防線：
  ```python
  # voice_tools.py execute()
  _VOICE_DENY_SUBSTR = ("empty trash", "rm -", "delete", "pay", "purchase")

  if name in ("click_xy", "type_text", "hotkey"):
      _frontmost_guard()          # 敏感 app 前景 → 拒絕
  if name == "type_text":
      low = arguments["text"].lower()
      if any(s in low for s in _VOICE_DENY_SUBSTR):
          return _err("action requires explicit typed confirmation; "
                      "voice-initiated destructive text is blocked")
  ```
  並考慮高風險工具（`click_xy`）加入「複誦確認」流程。

---

### A-08（Medium）`check_helper_allowed` 死碼；DH_* gate 可被腳本自行翻掉，文件未明說

- **位置：** `src/desktop_harness/safety.py:77-84`；`run.py`（未提供，見 A-21）
- **問題：**
  1. `check_helper_allowed()` 在可見程式碼中沒有任何呼叫者（PRE-RELEASE-REVIEW #1 也指證），`DH_SAFE` 對 runtime 沒有實質強制力，只是文件承諾；
  2. 產品本身是任意 `exec`（CLI stdin 腳本 / daemon exec）——任何腳本可以：
     ```python
     import os
     os.environ["DH_ALLOW_SENSITIVE"] = "1"   # 翻掉所有 sensitive gate
     import Quartz                              # 完全繞過 helpers
     ```
     gates 只防「誤用」，不防「腳本本身惡意」。SECURITY.md 有提 daemon 是 privileged exec endpoint，但沒有把這點講成對 **CLI 本身**也成立。
- **修補建議：**
  - 文件：SECURITY.md 加一段「任何經由 `desktop-harness` 執行的程式碼即以使用者全部權限執行；DH_* 環境變數僅規範內建 helpers，無法約束腳本本身。無人值守請使用專用非管理者帳號」；
  - 程式：要嘛把 `check_helper_allowed` 接進真實 gate（如 daemon namespace 建立時過濾高風險名稱），要嘛刪除死碼避免虛假安全感；
  - 可選縱深：daemon `namespace()` 不匯出 `os`/`subprocess`/`__import__`（提高門檻，非真正隔離——文件需如此描述）。

---

### A-09（Medium）相依套件無版本上限／無 hash pinning

- **位置：** `pyproject.toml:7-11`；`install.sh:11-15`
- **問題：**
  - `pyobjc-framework-*` 三個依賴完全未釘版本 → 未來 major 變更可能破壞 API（可靠性），且每次安裝解析到不同版本（再現性）；
  - `install.sh` 執行 `pip install -q -U pip`（升級到最新 pip，供應鏈面變大）且無 `--require-hashes` 鎖定。對一個「拿到 Accessibility 權限」的工具，安裝路徑的供應鏈風險值得保守處理。
- **重現方式：** 兩台機器不同時間跑 `install.sh` → 可能裝到不同版本 pyobjc/pip。
- **修補建議：**
  ```toml
  # pyproject.toml — 加下限 + 合理上限
  dependencies = [
    "pyobjc-framework-Quartz>=10,<12",
    "pyobjc-framework-Cocoa>=10,<12",
    "pyobjc-framework-ApplicationServices>=10,<12",
  ]
  ```
  ```bash
  # install.sh — 移除 -U pip（或釘版本），可選產出 requirements.lock 並 --require-hashes
  pip install -q "pip<26"
  ```

---

### A-10（Medium）`screenshot(path=...)` 為任意路徑寫入原語

- **位置：** `src/desktop_harness/capture.py:38-50`（`screenshot()` 的 `path` 參數）
- **問題：** 呼叫者可指定任意路徑，`path.write_bytes(...)` 會**覆蓋該使用者可寫的任何既有檔案**（例如 `~/.zshrc`、`~/.ssh/authorized_keys` 的內容換成 PNG 位元組——破壞性覆寫）。在「agent 腳本本來就是任意執行」的前提下（A-08）這不是新的權限邊界，但對 voice／受限呼叫者（voice tools 目前未暴露 screenshot，屬超前防護）以及未來 MCP 包裝，這是一個危險的寫入原語，且沒有路徑穿越／覆蓋檢查。
- **重現方式：** `desktop-harness <<'PY' screenshot(path="/tmp/anything.bin") PY` → 直接覆寫。
- **修補建議（保守）：** 拒絕覆蓋既有檔案、限制在暫存目錄（除非明確 opt-in）：
  ```python
  if path.exists():
      raise FileExistsError(f"refusing to overwrite existing file: {path}")
  resolved = Path(path).resolve()
  if not str(resolved).startswith(str(TMP)) and not os.environ.get("DH_ALLOW_ANY_PATH"):
      raise PermissionError(
          f"screenshot path outside {TMP} requires DH_ALLOW_ANY_PATH=1")
  ```

---

### A-11（Medium）daemon 單實例檢查 TOCTOU race

- **位置：** `src/desktop_harness/daemon.py:89-106`（PID 檢查與 socket unlink/bind）、`daemon.py:119`（PID 寫入）
- **問題：** 「讀 PID → 檢查存活 → probe → unlink → bind → 寫 PID」不是原子的。兩個 `daemon start` 同時執行都可能通過檢查，各自 unlink 再 bind，最後只剩一個 socket 檔案對應其中一個 process，另一個成為孤兡（持有舊 socket 的 fd 但不可達），且 PID 檔內容互相覆蓋。`daemon stop` 之後孤兡仍在跑。
- **重現方式：** 兩個終端機同時執行 `desktop-harness daemon start`（重複數次可觀察到 PID 檔與實際存活 process 不一致）。
- **修補建議：** 以 `fcntl.flock` 鎖檔做單實例（原子、跨 process）：
  ```python
  import fcntl
  LOCK_PATH = SOCKET_PATH.with_suffix(".lock")
  _lock_fh = LOCK_PATH.open("w")
  try:
      fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except BlockingIOError:
      raise SystemExit("daemon already running (lock held). Use: daemon stop")
  # 持有 lock 期間才 unlink stale socket + bind
  ```

---

### A-12（Low）token 比較非 constant-time

- **位置：** `src/desktop_harness/daemon.py:146`（`if req.get("token") != token:`）
- **問題：** 字串 `!=` 是短路的逐位元組比較，理論上可 timing side-channel。在「socket 已 0600、攻擊者需為同 UID」的實際條件下風險很低，但既然匯入了 `secrets`，改成 constant-time 是零成本縱深。
- **修補建議：**
  ```python
  import secrets
  if not secrets.compare_digest(str(req.get("token") or ""), token):
  ```

---

### A-13（Low）daemon 停止後 token 檔殘留

- **位置：** `src/desktop_harness/daemon.py:182-187`（`finally` 只 unlink `SOCKET_PATH`、`PID_PATH`）
- **問題：** `daemon stop` 後 `~/.desktop-harness/daemon.token` 留在磁碟上。檔案是 0600，同 UID 讀得到本來就是預期，但残留的 secrets 之一切原則是不需要就刪——尤其使用者可能把家目錄放進備份/同步。
- **修補建議：** `finally` 中一併 `TOKEN_PATH.unlink(missing_ok=True)`。

---

### A-14（Low）請求讀取無大小上限（server 與 client）

- **位置：** `src/desktop_harness/daemon.py:131-135`（server `while b"\n" not in buf`）；`client_request()` 同款迴圈
- **問題：** 沒有累積位元組上限，一個不送換行的巨量請求可讓 daemon（或 client）記憶體無限膨脹。同 UID 才連得上，風險低，但這是 DoS 衛生問題。
- **修補建議：**
  ```python
  MAX_REQ = 8 * 1024 * 1024
  while b"\n" not in buf:
      if len(buf) > MAX_REQ:
          conn.sendall(b'{"ok":false,"error":"request too large"}\n')
          break
      ...
  ```

---

### A-15（Low）`is_running()` 0.4s ping 逾時拖慢每次 CLI 呼叫

- **位置：** `src/desktop_harness/daemon.py:51-57`
- **問題：** socket 檔存在但 daemon 掛掉時，每次 CLI 呼叫都要等滿 400ms 才 fallback 到本地執行（PRE-RELEASE-REVIEW #10 已指出，現值仍是 0.4）。多步驟任務累積延遲明顯。
- **修補建議：** timeout 降到 0.1；`client_request` connect 失敗（`ConnectionRefusedError`/`FileNotFoundError`）時直接清理 stale socket 檔，避免後續每次都撞。

---

### A-16（Low）截圖暫存目錄權限取決於 TMPDIR

- **位置：** `src/desktop_harness/capture.py:15-16`（`TMP = Path(tempfile.gettempdir())/"desktop-harness"; TMP.mkdir(exist_ok=True)`）
- **問題：** macOS 預設 TMPDIR 是每使用者 0700 目錄，通常安全；但若使用者/環境把 `TMPDIR` 設成共用 `/tmp`，`desktop-harness` 子目錄會以預設 umask 建立，**含螢幕內容的截圖**就可被其他本地使用者讀取。截圖屬敏感產物，應明確設權限。
- **修補建議：**
  ```python
  TMP.mkdir(mode=0o700, exist_ok=True)
  os.chmod(TMP, 0o700)   # exist_ok 時 mkdir 不改既有目錄權限，需補 chmod
  ```

---

### A-17（Low）sensitive 子字串（bank/wallet/secrets）過廣且僅比對名稱

- **位置：** `src/desktop_harness/safety.py:20-29`（`_SENSITIVE_NAME_SUBSTR`）
- **問題：** `"bank"`、`"wallet"`、`"secrets"` 對**顯示名稱**做子字串比對：會擋 Apple Wallet（可能符合意圖），但也會誤擋名稱含這些字的一般 app／銀行網站包成的 app；反之bundle id 比對清單較準卻只涵蓋密碼管理器。誤擋會讓使用者習慣性設 `DH_ALLOW_SENSITIVE=1`，反而拆掉全部防線（fail-open 的社會工程學版本）。
- **修補建議：** bundle id 為主、顯示名稱精確比對為輔：
  ```python
  _SENSITIVE_NAME_EXACT = {"1password", "bitwarden", "keychain access",
                           "lastpass", "keepassxc", "dashlane", "nordpass"}
  # 名稱只做精確（或多一層 startswith），bank/wallet 只查 bundle id
  ```

---

### A-18（Low）voice session 工具呼叫迴圈無上限

- **位置：** `scripts/voice_session.py`（`run_session()` 的 `pending_calls` → `response.create` 邏輯）
- **問題：** 模型每輪回工具呼叫 → client 回 `response.create` → 模型再回工具呼叫……沒有輪數上限，模型若反覆呼叫（或在迴圈中重複破壞性動作），session 不會自止，成本與桌面副作用皆無界。
- **修補建議：** 加計數器，超過如 8 輪即中斷並回報使用者；每輪之間可加最短間隔。

---

### A-19（Info）`open -a` 使用 list-form subprocess — 無命令注入（通過）

- **位置：** `src/desktop_harness/windows.py`（`activate()` 的 `subprocess.run(["open", "-a", name], ...)`）
- **說明：** 以 list 形式呼叫、未經 shell，`name_or_bundle` 中的任何 shell metacharacter 都不會被解譯——命令注入面正確關閉。同樣地 daemon 協議為 JSON + `exec(compile(...))`（程式碼本來就是要執行的，注入概念不適用）。此項列為**通過**，提醒未來若有人「修正」成 `shell=True` 字串拼接即為高危回歸。
- 可留意點：`open -a <name>` 可啟動任意名稱的 app，僅受 sensitive 子字串過濾——屬設計使然（產品就是開 app 的工具）。

---

### A-20（Info）audit log 無 rotation／retention 政策

- **位置：** `src/desktop_harness/safety.py:86-93`
- **說明：** 長期 agent 使用下 `~/.desktop-harness/audit.jsonl` 無限成長（磁碟耗盡風險）；內容含 app 名稱、點擊目標與截圖路徑，無 retention/redaction 政策。目前 audit **不記錄** `set_field`/`type_text` 的值（對密碼是好事），應維持並明文寫進 SECURITY.md，避免未來「加強稽核」時把敏感值寫進 log。
- **建議：** 大小上限（如 5MB）+ 簡單輪替（改名 `.1` 保留一代）；文件記載路徑與保留政策。

---

### A-21（待驗證）未提供檔案的關鍵驗證項

以下檔案內容未包含在本任務提供的檔案集中，無法逐行稽核。依 `docs/PRE-RELEASE-REVIEW.md` 的歷史發現（#1、#6、#17、#21 等），這些是**必須人工或後續任務驗證**的項目：

| # | 待驗證項 | 檔案 | 依據 |
|---|----------|------|------|
| 1 | `click_text` / `click` / `type_text` / `hotkey` / `set_field` 是否**全部**呼叫 `check_frontmost_allowed()`（v0.4 新增了該函式，但是否接上所有 mutation 未證實） | `helpers.py`、`input.py` | PRE-RELEASE-REVIEW #1 |
| 2 | `run.py` 是否從 stdin 讀腳本後直接 `exec`（任意執行面，A-08 的前提） | `run.py` | 架構文件 |
| 3 | `check-update` 指令是否有對外網路請求、送出哪些資訊（phone-home 隱私） | `run.py` | README |
| 4 | `agent-workspace/agent_helpers.py` 載入路徑是否已改為 `~/.desktop-harness/` 下（repo 內 workspace = 每次執行任意碼的持久化載入點） | `helpers.py` | PRE-RELEASE-REVIEW #4 |
| 5 | `presence.py` 的執行緒使用是否遵守「AppKit 僅主執行緒」限制（OBSERVE-LOOP.md 記載違規會 SIGABRT 整個 process） | `presence.py` | docs/OBSERVE-LOOP.md |
| 6 | `ax.py` 的 `find`/`click` 座標計算是否有負值/超界防護（`frame_on_screen` 已存在於 selftest 測項，推測已處理） | `ax.py` | selftest |

---

## 整體 fail-open / fail-closed 盤點

| 控制點 | 行為 | 評語 |
|--------|------|------|
| daemon token 驗證 | fail-closed（缺 token 即拒） | ✅ 正確 |
| daemon token 檔不可讀時 client 不帶 token → server 拒 | fail-closed | ✅ 正確 |
| `check_app_allowed`（名稱比對） | fail-closed（raise） | ✅ |
| `check_frontmost_allowed` 例外時 | **fail-open** | ❌ A-03 |
| `audit()` 寫入失敗 | **fail-open（靜默）** | ❌ A-04 |
| 截圖 gate（可見但非前景視窗） | **fail-open（漏檢）** | ❌ A-05 |
| `is_running()` 例外 → fallback 本地執行 | 降級可接受，但無告警 | ⚠️ |
| voice executor 對模型指令 | **無 runtime 強制（fail-open）** | ❌ A-07 |

## 機密掃描結果

- 提供的檔案中**未發現**任何真實 token、API key、密碼或個資。`XAI_API_KEY` 僅以環境變數讀取（`scripts/voice_session.py`），文件中的 `'YOUR_KEY_HERE'` 為明確佔位符，符合規範。
- `.gitignore` 已涵蓋 `*.png`，可降低誤 commit 螢幕截圖的風險；建議再補 `daemon.token`、`*.pid`、`audit.jsonl`（若曾在 repo 內測試）。
- 測試所需的任何假憑證一律使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串（本報告未需要）。

*本報告僅新增於 `docs/fmb-security/`，未修改任何既有檔案。*
