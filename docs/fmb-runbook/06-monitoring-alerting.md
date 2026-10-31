# 監控與告警建議

> desktop-harness 是單機本機工具，無遠端服務；監控目標是「本機健康 + 安全痕跡」。以下為建議，repo 本身未內建監控系統。

## 應監控的訊號

| # | 訊號 | 來源 | 建議閾值 / 意義 |
|---|------|------|----------------|
| 1 | doctor 檢查結果 | 定時跑 `desktop-harness --doctor`（解析 PASS/FAIL 行數） | 任何 FAIL → 告警（先修第一個 FAIL） |
| 2 | selftest 結果 | 部署/更新後跑一次（含 GUI 動作，不宜高頻） | 任何 FAIL → 告警 |
| 3 | daemon 存活 | `desktop-harness daemon status` 退出碼 | 預期常駐卻 down → 告警 |
| 4 | CLI 呼叫延遲 | 每次 agent 呼叫耗时 | fallback 至 in-process 且顯著變慢 → 檢查殘留 socket（F4） |
| 5 | token / socket 檔權限 | `stat` 檢查 mode | **非 0600 → 立即高危告警**（安全事件） |
| 6 | audit log 成長率 | 檔案 size / 行數趨勢 | 暴增 = 異常密集操作；長期只增不減 = 需輪替 |
| 7 | 版本一致性 | `--version` vs `pyproject.toml` | 不一致 → 告警（更新不完整） |
| 8 | `DH_ALLOW_SENSITIVE` 狀態 | 環境變數是否被設為啟用 | 任何非預期啟用 → 告警並確認授權來源 |

## 建議作法（本機 crontab / launchd）

- **每日一次** L1–L2 巡檢：跑 `--doctor`，非零退出碼即通知（例如本地通知 `osascript -e 'display notification …'`、或現有內部告警渠道）。
- **每 5 分鐘**（若依賴 daemon）：`daemon status` 存活檢查 + 檔案權限檢查（訊號 3、5）。
- **每週**：audit log 大小檢查；超過約定的保留上限（由維運決策，例如 50 MB）時輪替（`mv` + 壓縮保存於本地，**不上傳**——內容可能含敏感操作摘要）。
- 注意：監控腳本本身若呼叫 `selftest`，會產生真實 GUI 動作——**不要**排在高頻排程。

## 告警分級建議

| 級別 | 條件 | 動作 |
|------|------|------|
| **P0（安全）** | token/socket 權限偏離 0600；audit log 出現非預期敏感 App 操作 | 立即 `daemon stop`、保存 audit log、通知負責人，參照 [05-rollback.md](./05-rollback.md) 安全事件程序 |
| **P1（功能）** | doctor/selftest FAIL；daemon 預期常駐卻 down | 依 [04-troubleshooting.md](./04-troubleshooting.md) 對應條目處置 |
| **P2（容量/維護）** | audit log 超上限；版本不一致 | 排程輪替 / 補跑 `install.sh` |

## 紀錄與留存

- audit log 是主要的事後鑑識來源：append-only、本地保存、輪替副本同樣僅本地。
- 告警訊息**不得**包含畫面截圖內容、密碼、個資；只帶檢查名稱與 PASS/FAIL。
- 開 issue 回報問題時，附 `--doctor` + `selftest` 輸出（去除敏感內容）。

## 明確不建議

- 不建議把 audit log 或截圖同步到任何外部服務。
- 不建議無人值守長跑（unattended / always-approve）搭配 daemon 常駐——SECURITY.md 的既有建議。
- 不建議自動化重啟 daemon 來「修」未知故障；先診斷（F4/F5）再重啟。
