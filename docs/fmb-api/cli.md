# CLI 參考：`desktop-harness`

`desktop-harness` 是產品的主要介面——**不是 MCP server**，而是一個本機 CLI（見 [ADR-0002](../fmb-adr/ADR-0002-cli-not-mcp.md)）。Agent 以 shell 呼叫，腳本透過 stdin（heredoc）餵入 Python。

進入點：`desktop_harness.run:main`（見 [pyproject.toml](../../pyproject.toml) `[project.scripts]`）。

## 全域行為

- **stdin 腳本模式**：不帶子命令時，CLI 從 stdin 讀取 Python 腳本，組裝 helper 命名空間（含 `agent-workspace/agent_helpers.py`）後執行。預設會自動改用常駐 daemon（若已在跑）；`DH_NO_DAEMON` 可强制本機行程。腳本的 stdout／stderr 會回傳給呼叫端。
- **版本**：`--version` 印出版本字串（目前 `0.4.2`，見 `src/desktop_harness/__init__.py`）。
- **結束碼**：成功為 `0`；健檢／自測有失敗項目時為非 0。

## 指令總覽

| 指令 | 用途 | 破壞性 |
|------|------|--------|
| `desktop-harness <<'PY' … PY` | 執行一段 Python 控制腳本 | 依腳本 |
| `desktop-harness --version` | 印出版本 | 無 |
| `desktop-harness --doctor` | 權限與環境健檢 | 無 |
| `desktop-harness selftest` | 非破壞性自我測試 | 低（會動滑鼠／開 TextEdit） |
| `desktop-harness demo` | 可見煙霧測試 | 中（移動真實滑鼠、開 TextEdit、打字） |
| `desktop-harness skill` | 輸出 `SKILL.md` 到 stdout | 無 |
| `desktop-harness daemon start [--bg]` | 啟動常駐 daemon | 無 |
| `desktop-harness daemon status` | 查詢 daemon 狀態 | 無 |
| `desktop-harness daemon stop` | 停止 daemon | 無 |
| `desktop-harness check-update` | 與 GitHub main 比對版本 | 無（需網路） |

---

## stdin 腳本模式

```bash
desktop-harness <<'PY'
print(mouse_pos())
open_app("Safari")
print(labels()[:10])
PY
```

- **說明**：預設路由到常駐 daemon（較快）；daemon 未啟動或 `DH_NO_DAEMON` 啟用時改為本機行程。
- **前置條件**：已授予 Accessibility（讀 AX、注入鍵鼠）；截圖另需 Screen Recording。
- **錯誤**：敏感 app 被阻擋時拋 `PermissionError`（見 [configuration.md](./configuration.md) `DH_ALLOW_SENSITIVE`）。

## `--version`

- **用途**：印出目前已安裝版本。
- **用法**：`desktop-harness --version`
- **回傳**：版本字串（stdout）。

## `--doctor`

- **用途**：驗證 PyObjC 載入、Accessibility（`AXIsProcessTrusted`）、Screen Recording（實拍一張並驗證檔案大小）、前景 app AX 節點數、視窗列表（對應 `admin.run_doctor()`）。
- **用法**：`desktop-harness --doctor`
- **副作用**：會嘗試截一張圖（非破壞）。
- **回傳／結束碼**：逐項印 PASS／FAIL；全過為 `0`，否則非 0。

## `selftest`

- **用途**：非破壞性自測——先跑 doctor，再測核心 helper、滑鼠移動後復原、截圖、`media_transport` API、`find_app` 排序、`frame_on_screen`、TextEdit 開啟＋打字、daemon 背景啟動與 exec 往返（對應 `selftest.run_selftest()`）。
- **用法**：`desktop-harness selftest`
- **副作用**：會移動真實滑鼠並開啟 TextEdit；daemon 往返測試可能影響你已在跑的 daemon（測試隔離議題，見 [fmb-perf TR-6](../fmb-perf/findings-timeouts-recovery.md)）。
- **結束碼**：全過為 `0`，否則非 0。

## `demo`

- **用途**：可見煙霧測試——開 TextEdit、`cmd+n`、移滑鼠進視窗、`wiggle`、`click`、打字、印 labels，最後收起 presence（對應 `demo.run_demo()`）。
- **用法**：`desktop-harness demo`
- **副作用**：**會移動你的真實滑鼠並開啟 TextEdit**；需人工觀看。
- **回傳**：`0`。

## `skill`

- **用途**：把內建 `SKILL.md` 輸出到 stdout，供安裝腳本註冊 Grok skill（`install.sh` 會導向 `~/.grok/skills/desktop-harness/SKILL.md`）。
- **用法**：`desktop-harness skill > ~/.grok/skills/desktop-harness/SKILL.md`

## `daemon`（子命令）

常駐溫熱进程，讓多步任務不必重複 import PyObjC。協定細節見 [daemon-protocol.md](./daemon-protocol.md)。

| 子命令 | 說明 |
|--------|------|
| `daemon start` | 前景啟動 daemon |
| `daemon start --bg` | 背景啟動 daemon |
| `daemon status` | 回報是否運行、PID |
| `daemon stop` | 停止 daemon |

- **安全**：socket 與 token 檔皆為 `0600`；僅同 UID 可用。多人共用機器請勿常開（見 [SECURITY.md](../../SECURITY.md)）。
- **建議**：長会话結束後 `desktop-harness daemon stop`。

## `check-update`

- **用途**：將本機版本與 GitHub `main` 比對（選用）。**不會**自動更新——會動滑鼠的程式碼更新由使用者自己決定。
- **用法**：`desktop-harness check-update`
- **前置條件**：需可連線 GitHub。
