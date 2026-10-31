# desktop-harness 維運手冊（fmb-runbook）

本目錄是 `desktop-harness`（v0.4.2）的維運 runbook，依主題分檔：

| 檔案 | 主題 |
|------|------|
| [01-install-deploy.md](./01-install-deploy.md) | 安裝與部署步驟 |
| [02-config.md](./02-config.md) | 設定項說明（環境變數） |
| [03-health-checks.md](./03-health-checks.md) | 健康檢查 |
| [04-troubleshooting.md](./04-troubleshooting.md) | 常見故障：症狀 → 診斷 → 處置 |
| [05-rollback.md](./05-rollback.md) | 回滾程序 |
| [06-monitoring-alerting.md](./06-monitoring-alerting.md) | 監控與告警建議 |

## 適用範圍與假設

- 作業系統：macOS（建議 Sequoia 以上），Python 3.10+。
- 元件：本機 CLI（`desktop-harness`）、選配的 warm daemon（Unix socket + token）、選配的 voice 實驗腳本（`scripts/voice_session.py`）。
- 關鍵路徑：
  - 安裝目標：repo 內 `.venv/`、`~/.local/bin/desktop-harness` shim
  - 執行期資料：`~/.desktop-harness/`（audit log、daemon token、agent workspace）
  - daemon socket/PID：`~/Library/Caches/desktop-harness/`（`daemon.sock` / `daemon.pid`）
- 安全前提：daemon 是「本機具權限的 exec 端點」（socket 與 token 權限 0600），僅限單一使用者機器使用；詳見 repo 的 `SECURITY.md`。

## 維運速記（TL;DR）

```bash
desktop-harness --doctor        # 權限與依賴健檢
desktop-harness selftest        # 非破壞性自測（含 GUI 動作與 daemon 往返）
desktop-harness daemon status   # daemon 狀態
desktop-harness --version       # 版本確認
```

升級 → `05-rollback.md` 內含「先停 daemon」的完整順序。
