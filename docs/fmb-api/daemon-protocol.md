# Daemon 通訊協定與 API

常駐 daemon 讓多步任務不必重複 import PyObjC。它是**本機特權 exec 端點**：能連上 socket 並持有 token 的同 UID 行程可執行任意 Python——不應在多人共用機器上常開（[SECURITY.md](../../SECURITY.md)）。

## 傳輸與安全

- **傳輸**：AF_UNIX stream socket 上的 **NDJSON**（每行一個 JSON 物件）。
- **檔案權限**：socket 檔與 token 檔皆為 `0600`；PID 檔用於單一實例。預設位置見 [ARCHITECTURE.md §4.3](../fmb/ARCHITECTURE.md)。
- **覆寫路徑**：socket 以 `DH_SOCKET`、token 以 `DH_TOKEN_PATH` 覆寫（見 [configuration.md](./configuration.md)）。
- **認證**：`exec` 前必須驗證 token；缺 token 或錯誤即拒。

## 操作（op）

| op | 請求 | 回應 | 說明 |
|----|------|------|------|
| `ping` | `{"op":"ping"}` | `{"ok":true,…}` | 存活探測；`is_running()` 以約 0.4s 逾時 ping。 |
| `exec` | `{"op":"exec","code":"<python>","token":"<token>"}` | `{"ok":true,"stdout":"…","stderr":"…"}` | 在常駐进程內 `exec()` 腳本；必須帶 token。 |
| `quit` | `{"op":"quit",…}` | 依實作 | 停止 daemon。 |

- `code` 為要執行的 Python 原始碼；`stdout`／`stderr` 為腳本輸出。
- 範例（token 用假值）：
  ```json
  {"op":"exec","code":"print(labels()[:5])","token":"FAKE_VALUE_FOR_TEST"}
  ```

## Python API（`desktop_harness.daemon`）

| 函式 | 說明 |
|------|------|
| `serve()` | 啟動 daemon 主迴圈（accept + 處理連線）。 |
| `client_request(obj)` | 向 daemon 送一個請求物件，回傳解析後的回應 dict。 |
| `exec_via_daemon(code)` | 以 daemon 執行腳本並取回 `{ok, stdout, stderr}`。 |
| `is_running()` | 以 socket ping 判斷 daemon 是否存活。 |
| `stop()` | 要求 daemon 停止。 |

## CLI

```bash
desktop-harness daemon start --bg   # 背景啟動
desktop-harness daemon status
desktop-harness daemon stop
```

## 已知限制（誠實條目）

- 單執行緒 accept 迴圈、連線無逾時、`exec` 無伺服端逾時——單一卡住的 client 可能讓 daemon 無回應（[fmb-perf DAEMON-1/2/3](../fmb-perf/findings-daemon.md)）。
- daemon 掛掉但 socket 殘留時，每次 CLI 呼叫可能多付約 0.4s（[fmb-perf DAEMON-4](../fmb-perf/findings-daemon.md)）。
- 上述為追蹤中的議題，非本文件的行為保證。
