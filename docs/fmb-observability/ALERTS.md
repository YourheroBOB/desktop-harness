# 告警條件與處置

> 哲學：**本地優先、無 pager**。desktop-harness 是單機工具，告警的多數合理型態是「下一次人類看終端機／跑 report 時就看見」，而不是 24/7 on-call。
> 嚴重度：P1 = 立即可見且通常已無法工作；P2 = 當天處理；P3 = 記入待辦。

## 1. 告警總表

| ID | 條件 | 窗口／閾值（初值） | 嚴重度 | 可能原因 | 處置 |
|----|------|--------------------|--------|----------|------|
| ALRT-01 | `doctor_check{status=fail}` 任一項 | 單次執行 | **P1** | Accessibility／Screen Recording 未授權或被撤銷；pyobjc 毀損 | 依 `admin.py` 輸出開設定 pane；授權後**完整重啟** host app；紀錄於事件 |
| ALRT-02 | `selftest_step{status=fail}` | 單次執行 | **P1** | 上述任一 + TextEdit/daemon 路徑毀壞 | 先 `DH_NO_DAEMON=1` 重跑定位；附 doctor+selftest 輸出回報 |
| ALRT-03 | daemon ping 連續失敗 ≥ 3，或 `daemon_stale_socket` | 5 分鐘 | P2 | daemon 僵死／socket 殘留（REVIEW #10） | 落地 ROADMAP #8：刪 stale sock、PID 檔存活檢查；必要時 `daemon stop` |
| ALRT-04 | `safety_block` 風暴 | > 20 次／小時 | P2 |  agent 持續操作敏感 app；或敏感清單誤殺（REVIEW #19：`wallet`/`bank` 過寬） | 檢查是哪個 gate；若是誤殺，推動改以 bundle id 比對（REVIEW #19） |
| ALRT-05 | 錯誤率突增 | error/動作 > 5%，10 分鐘窗口 | P2 | 權限被撤、系統更新、pyobjc 版本 | 依 `dh_errors_total{class,module}` 取 top class 排查 |
| ALRT-06 | 隱私掃描命中 forbidden 樣式 | 任何一次 | **P1** | 程式把內容級資料寫入事件／log | **停止寫入 events.jsonl**、保全現場、修復並補測試後才恢復；见 `SENSITIVE-FIELDS.md` |
| ALRT-07 | `audit_write_failed` 出現 | 任何一次 | P2 | 磁碟滿／權限／路徑無效 | 觀測性已受損：修復前所有 SLO 數據不可信 |
| ALRT-08 | events/audit 檔 > 5MB 未輪替 | 每日檢查 | P3 | 輪替未落地 | ROADMAP #7 |
| ALRT-09 | SLO 連續 3 日未達（SLO-1/3/4/5） | 每日報告 | P3 | 效能退化 | REVIEW #9（重複 AX walk）、#13（固定 sleep） |
| ALRT-10 | `safety_override` 非零且伴隨 mutation | 每日報告 | P2 | 有人設了 `DH_ALLOW_SENSITIVE=1` | 確認是人為測試；非預期則調查腳本來源 |

## 2. 閘門完整性專用檢查（SLO-8 的落地方式）

每次 report 執行一比對：

```
對同一 session_id 的時間序列：
  若存在 safety_block 事件，其後 1 秒內不得出現同 target 的 mutating 事件
  命中 → dh_gate_bypass_events_total++ → ALRT-04 升級為 P1
```

對應 PRE-RELEASE-REVIEW #1 的核心擔保：「文件宣稱的阻擋，必須在事件流裡可被證明」。

## 3. 通知管道（本地）

| 管道 | 用途 |
|------|------|
| stderr 摘要 | CLI 結束時一行健康狀態（如 `[observability] 2 warns, 0 errors`） |
| `desktop-harness report`（提案） | 人類主動查看的儀表板，見 `DASHBOARD.md` |
| `--doctor` 輸出 | 授權類問題的第一現場 |
| 檔案標記 | 事件檔內 `level=warn/error` 行，供 `jq` 過濾 |

**不送外部**：沒有 webhook、沒有郵件、沒有推送。若未來 BOB 決定接自有監控（如 self-hosted Grafana / Loki），必須另外做：明確 opt-in 文件、傳輸前再過一次 `SENSITIVE-FIELDS.md` 紅線、並預設只送計數類指標（不送事件原文）。此項列為「需要 BOB 決策」。

## 4. 告警自身的健康

- 告警規則本身也要版本化（本文件版本號）。
- 若 `audit_write_failed` 出現（ALRT-07），所有其他告警降級為「不可信」，因為它們共用同一條觀測管路。
