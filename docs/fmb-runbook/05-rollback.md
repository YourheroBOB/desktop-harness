# 回滾程序

## 觸發條件

- 更新後 `--doctor` / `selftest` 出現原本沒有的 FAIL
- agent 任務行為異常且排查（[04-troubleshooting.md](./04-troubleshooting.md)）無法於時限內解決
- 發現安全事件（token / socket 權限異常、audit log 出現非預期動作）
- 需要暫時回到上一個已知良好版本

## 回滾原則

1. **先停 daemon**：daemon 常駐程序持有舊版命名空間與 helpers，不停它等於沒回滾。
2. 回滾的是「工作樹 + venv + shim」，三者需一致（`install.sh` 一次處理）。
3. `~/.desktop-harness/` 下的執行期資料（audit log）**不刪**，保留供調查。
4. 回滾後必須完整健檢。

## 程序（git 版本回滾）

```bash
cd /path/to/desktop-harness

# 1. 停止 daemon
desktop-harness daemon stop
# 若 daemon 無回應：手動清 socket/pid 殘檔（見 04-troubleshooting.md F4）

# 2. 記錄現況（供事後分析，不推送）
git log --oneline -5 > /tmp/dh-rollback-notes.txt
desktop-harness --version >> /tmp/dh-rollback-notes.txt

# 3. 回到上一個已知良好版本（保守作法：回到 tag 或前一 commit）
git checkout <已知良好版本：tag 或 commit>
# 沒有 tag 時：git checkout HEAD~1（僅本地，不 push / 不 merge）

# 4. 重建 venv + shim + skill
./install.sh

# 5. 權限與功能驗證
desktop-harness --version
desktop-harness --doctor
desktop-harness selftest

# 6. 健康後再視需求重啟 daemon
desktop-harness daemon start --bg
desktop-harness daemon status
```

## 緊急停止（不需要回滾、只需立刻止損）

```bash
desktop-harness daemon stop        # 關閉常駐 exec 端點
```

- 之後 CLI 每次呼叫會走 in-process（較慢但仍可用）；若要完全停用工具，移除 PATH 上的 shim 或不讓 agent 呼叫。
- 人類隨時可實體搶回滑鼠／鍵盤——physical input 永遠優先。

## 安全事件時的額外步驟

1. `daemon stop`（即重寫/失效化 token 路徑）。
2. 保存 `audit.jsonl` 副本（注意：內容可能含敏感操作記錄，僅本地保存、勿外傳）。
3. 檢查 socket / token 檔權限是否曾偏離 0600。
4. 完成調查前**不**重啟 daemon；必要時暫時用 `DH_NO_DAEMON`（設為啟用）維持最低功能。

## 回滾後行動

- 在本地分支記錄回滾原因（commit message 或筆記），**不 push、不 merge**（依維運邊界）。
- 若確認是新版缺陷：整理重現步驟（`--doctor` + `selftest` 輸出，去除敏感內容）回報。
