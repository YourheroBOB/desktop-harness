# 02 · CLI 與 daemon（FAQ B1–B8）

## B1 · heredoc 腳本沒輸出或語法錯

- **問題：** `desktop-harness <<'PY' … PY` 執行後沒有預期輸出，或噴語法錯誤。
- **原因：** 最常見是 heredoc 終止符不對——開頭用了 `<<'PY'`（單引號，不做變數展開），結尾的 `PY` 必須頂行、前後不能有空白。另一種是腳本內縮排混用 tab／空格。
- **解法：** 確認結尾 `PY` 獨立一行且無縮排；腳本內統一縮排。要印結果記得 `print(...)`（stdout 會回傳給 agent）。
- **相關檔案：** `src/desktop_harness/run.py`（stdin 讀取）、`SKILL.md`、`README.md`（範例）。

## B2 · daemon start 後 status 仍是 stopped / 第二次 start 被拒

- **問題：** `daemon start --bg` 之後 `daemon status` 顯示沒在跑；或重複 start 被拒絕。
- **原因：** (a) PID 檔單一實例檢查——已在跑會拒絕再啟動；(b) 先前異常結束留下 stale socket／pid 檔（SIGTERM 不會走 `finally` 清理，見 fmb-perf DAEMON-6）；(c) `--bg` 模式下啟動失敗的錯誤不會印在前台。
- **解法：** 先 `desktop-harness daemon stop`（會清理），必要時確認 `~/Library/Caches/desktop-harness/daemon.pid` 指向的行程已不存在後刪除 stale 檔，再 `daemon start --bg`。日常先 `daemon status` 再決定。
- **相關檔案：** `src/desktop_harness/daemon.py`、`docs/fmb-perf/findings-daemon.md`（DAEMON-5/6）、`docs/fmb-adr/ADR-0004-warm-daemon-token-auth.md`。

## B3 · 每次呼叫都多等約 400ms

- **問題：** daemon 明明已經掛掉（或 socket 檔殘留），但每個 CLI 呼叫都卡約 0.4 秒才 fallback 到 in-process。
- **原因：** `run.py` 每次都對 socket 做 ping，timeout 0.4s；socket 檔存在但 daemon 死掉時，這 0.4s 是白等的，且連線失敗不會清掉 stale socket（fmb-perf DAEMON-4）。
- **解法：** 立即緩解：`desktop-harness daemon stop` 清掉 stale socket。長期解法（ping timeout 降至 50–100ms + PID 存活預檢）已在 `docs/fmb-perf/findings-daemon.md` 列為 P1 建議。暫時不想付 ping 成本可 `DH_NO_DAEMON=1`。
- **相關檔案：** `src/desktop_harness/run.py`、`src/desktop_harness/daemon.py`、`docs/fmb-perf/findings-daemon.md`。

## B4 · daemon 突然整個無回應

- **問題：** daemon 起著，但所有請求都沒回應。
- **原因：** v0.4.2 的 daemon 是**單執行緒 accept 迴圈、連線無逾時**——一個掛住的 client（連上但不送資料）或連線處理中未捕捉的 socket 例外會讓整個 daemon 卡死／終結（fmb-perf DAEMON-1、DAEMON-2，P0 級已知問題）。另外 exec 無伺服器端逾時（DAEMON-3），一個長跑腳本會佔住 daemon。
- **解法：** `desktop-harness daemon stop`（必要時直接 kill 該 PID 再清 stale 檔）後重啟。修復（連線逾時 + 例外捕捉 + exec timeout）為 fmb-perf 建議的優先 PR；在那之前，避免讓單一腳本在 daemon 內跑超長時間，或對長任務改用 `DH_NO_DAEMON=1` 的 in-process 路徑。
- **相關檔案：** `src/desktop_harness/daemon.py`、`docs/fmb-perf/findings-daemon.md`（DAEMON-1/2/3）。

## B5 · 改了 `agent-workspace/agent_helpers.py` 沒生效

- **問題：** 在 agent workspace 加了自訂 helper，但腳本裡呼叫不到或行為是舊的。
- **原因：** daemon 的 namespace 在建置時**只載入一次**；agent workspace 的修改需要 daemon 重啟才會反映（review #16，ADR-0004 已明文）。
- **解法：** `desktop-harness daemon stop && desktop-harness daemon start --bg`。或暫時用 `DH_NO_DAEMON=1` 跑 in-process（每次都重新載入）驗證新 helper。
- **相關檔案：** `agent-workspace/agent_helpers.py`、`src/desktop_harness/daemon.py`、`docs/fmb-adr/ADR-0003-arbitrary-exec-surface.md`、`docs/fmb-adr/ADR-0004-warm-daemon-token-auth.md`。

## B6 · 想強制不走 daemon

- **問題：** 希望某次呼叫一定在獨立行程執行（除錯、避免 daemon 狀態干擾）。
- **原因：** 預設行為是 socket 存在且 daemon 活著就自動路由經 daemon。
- **解法：** `DH_NO_DAEMON=1 desktop-harness <<'PY' … PY`，一律 in-process。其他環境開關見 `README.md`（`DH_MOUSE_INSTANT`、`DH_PRESENCE`、`DH_SAFE`、`DH_ALLOW_SENSITIVE`）。
- **相關檔案：** `src/desktop_harness/run.py`、`README.md`、`docs/fmb/ARCHITECTURE.md`（§3.4）。

## B7 · 跑 selftest 後 daemon 被停掉了

- **問題：** 自己開著的 daemon 在跑完 `desktop-harness selftest` 後不見了。
- **原因：** selftest 的 daemon roundtrip 測試會停掉使用者**正在跑**的 daemon，改變全域狀態（fmb-perf TR-6，P2 級已知問題）。
- **解法：** selftest 後重新 `desktop-harness daemon start --bg`。長期修法（測試前記錄狀態、測試後還原）已在 `docs/fmb-perf/findings-timeouts-recovery.md` 列為建議。
- **相關檔案：** `src/desktop_harness/selftest.py`、`docs/fmb-perf/findings-timeouts-recovery.md`（TR-6）、`docs/fmb-perf/verification-plan.md`（§1）。

## B8 · daemon 的 socket / token 檔在哪？測試怎麼隔離？

- **問題：** 想知道 daemon 的執行期檔案位置，或寫測試時不想碰使用者真正的 daemon。
- **原因：** 預設路徑是全域的：socket 與 pid 在 `~/Library/Caches/desktop-harness/`，token 在 `~/.desktop-harness/daemon.token`（皆 0600）。
- **解法：** 用環境變數覆寫指向暫存目錄：`DH_SOCKET`、`DH_TOKEN_PATH`（audit 用 `DH_AUDIT_LOG`），並設 `DH_NO_DAEMON=1` 避免碰使用者 daemon。測試前先記錄真實 `daemon status`、測試後確認不變。這是 `docs/fmb-perf/verification-plan.md` 的共通原則。
- **相關檔案：** `src/desktop_harness/daemon.py`、`docs/fmb-perf/verification-plan.md`、`docs/fmb/ARCHITECTURE.md`（§4.3）。
