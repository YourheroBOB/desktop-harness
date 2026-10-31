# 設定項說明

所有設定皆透過環境變數。本檔只說明**變數名稱與用途**，不記錄任何實際值。

## 核心行為

| 變數 | 用途 |
|------|------|
| `DH_NO_DAEMON` | 設定時一律走 in-process，不嘗試連 warm daemon（排查 daemon 問題、或強制乾淨程序時用） |
| `DH_MOUSE_INSTANT` | 設定時滑鼠瞬移、無動畫 |
| `DH_PRESENCE` | 控制 presence UI（藍色光環 + 「Agent active — hands off」提示條）開關；預設為啟用 |
| `DH_SAFE` | Agent 安全模式政策開關（預設啟用；停用前請先閱讀 SECURITY.md） |
| `DH_ALLOW_SENSITIVE` | 允許對「疑似密碼管理器類」App 進行 open / focus / 變更 / 截圖。**預設關閉**；非必要勿開 |

## 路徑覆寫

| 變數 | 用途 |
|------|------|
| `DH_SOCKET` | daemon Unix socket 路徑覆寫（預設在使用者快取目錄下） |
| `DH_TOKEN_PATH` | daemon token 檔路徑覆寫（預設在 `~/.desktop-harness/` 下） |
| `DH_AUDIT_LOG` | audit log（JSONL）路徑覆寫（預設 `~/.desktop-harness/audit.jsonl`） |
| `DH_AGENT_WORKSPACE` | agent 自訂 helpers 目錄覆寫（預設指向 repo 的 `agent-workspace/`） |

## Voice（實驗性、選配）

| 變數 | 用途 |
|------|------|
| `XAI_API_KEY` | Grok Voice Realtime API 金鑰（Voice 路徑專用；**Grok Build 登入不等同此 key**）。只放環境變數或 Keychain，不得寫入任何檔案 |
| `GROK_VOICE_MODEL` | Voice session 使用的模型名稱覆寫 |

## 重要檔案（非變數，但屬設定面）

| 路徑 | 說明 |
|------|------|
| `~/.desktop-harness/audit.jsonl` | 關鍵變更動作的審計記錄（append-only，無輪替機制 — 見監控建議） |
| `~/.desktop-harness/daemon.token` | daemon 認證 token（0600；daemon 啟動時重寫） |
| daemon socket / pid 檔 | 位於使用者快取目錄下，權限 0600；daemon 停止時自動清理 |
| `agent-workspace/agent_helpers.py` | agent 自訂 helpers；daemon 啟動時載入一次，**修改後需重啟 daemon 才生效** |
| `~/.grok/skills/desktop-harness/SKILL.md` | Grok Build skill 註冊檔 |

## 設定變更原則

1. 變更任何 `DH_*` 變數後，先跑 `desktop-harness --doctor` 與 `selftest` 驗證。
2. 涉及 daemon 行為的變數（路徑覆寫等）需 `daemon stop` → 變更 → `daemon start --bg`。
3. `DH_ALLOW_SENSITIVE` 屬高風險開關，僅在明確任務需求、單人機器、有人監看時暫時開啟，任務結束即關閉。
4. 永不把金鑰類變數的值寫進 shell 設定檔以外的版本控管檔案。
