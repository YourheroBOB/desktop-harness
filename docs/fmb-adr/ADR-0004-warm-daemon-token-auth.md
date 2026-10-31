# ADR-0004：常駐 warm daemon + Unix socket + token 認證

**狀態：** 接受中（token 認證是後補的硬化，源自 code review critical #2）  
**相關模組：** `daemon.py`、`run.py`（自動路由）

## 背景

每次 CLI 呼叫都要冷啟動 Python + 匯入 pyobjc，多步任務會重複付這個成本。解法是常駐一個 warm process。但一個「能執行任意 code、且持有 Accessibility 權限」的常駐 endpoint，本質上是**本機特權執行端點**——第一版（見 `docs/PRE-RELEASE-REVIEW.md` #2）沒有認證，任何同 UID process 連上 socket 就能完全控制桌面，被列為 critical。

## 決策

- daemon 以 Unix socket（NDJSON 協定：一行請求、一行回應）提供 `exec`/`ping`/`quit`。
- **認證**：啟動時產生 `secrets.token_hex(24)` 寫到 `~/.desktop-harness/daemon.token`（mode 0600）；每個請求必須帶 token，不符即拒。
- **socket 權限**：bind 後 `os.chmod(SOCKET_PATH, 0o600)`。
- **單一實例**：PID file + `os.kill(pid, 0)` 存活檢查；已在跑則拒絕啟動。
- CLI 端：socket 存在時自動路由 script 經 daemon（快），daemon 掛了自動退回 in-process；`DH_NO_DAEMON=1` 強制本地執行。

## 取捨

- token 檔**與 socket 同為 0600、同 UID 可讀**——它防的是「其他使用者/無權限 process」，防不了同帳號下的惡意程式（它本來就有同等權限）。這是務實的界限：追求更強隔離就要 sandbox/agent profile，超出本專案範圍。
- 選 token 檔而非 `SO_PEERCRED` peer credential 檢查：token 簡單、可跨 CLI/daemon 版本運作；代價是 token 檔成為新的敏感物，必須 0600 且不出 `~/.desktop-harness`。
- daemon 的 namespace 只在建置時載入一次：改了 `agent-workspace/agent_helpers.py` 需要 daemon restart 才生效（文件已註明；review #16）。

## 後果

- 多步任務第二步起顯著變快；`selftest` 有一條 daemon bg + exec 往返測試。
- `SECURITY.md` 明言：不要在共享多用戶機器上跑 daemon 而不理解其風險；長 session 結束建議 `daemon stop`。
- socket 路徑（`~/Library/Caches/desktop-harness/daemon.sock`）與 token 路徑可用 `DH_SOCKET` / `DH_TOKEN_PATH` 覆寫，測試時應指向 tmp 目錄。
- 歷史包袱：daemon 問題的教訓（「先求有、後補 auth」）已固化為此 ADR——**任何新的常駐 endpoint 從第一天就要有認證**。
