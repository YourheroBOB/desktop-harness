# 健康檢查

## 分層健檢模型

| 層級 | 檢查 | 指令 / 方法 | 健康標準 |
|------|------|-------------|----------|
| L1 依賴 | pyobjc frameworks | `desktop-harness --doctor`（第一項） | PASS |
| L1 權限 | Accessibility | `--doctor` | PASS |
| L1 權限 | Screen Recording（實拍一張 >1KB 圖） | `--doctor` | PASS |
| L2 感知 | AX snapshot（frontmost app） | `--doctor` | 節點數 > 0 |
| L2 感知 | 視窗列表 | `--doctor` | 至少 1 個視窗 |
| L3 功能 | 核心 helpers + GUI 煙霧測試 | `desktop-harness selftest` | 全部 PASS |
| L4 daemon | 狀態 / ping / exec 往返 | `desktop-harness daemon status`；selftest 內建 daemon 往返 | 回應 ok |
| L5 版本 | 版本一致性 | `desktop-harness --version` 對照 `pyproject.toml` | 一致 |

## 日常巡檢（建議頻率：每次長任務前／每日一次）

```bash
desktop-harness --doctor
desktop-harness daemon status
desktop-harness --version
```

## 深度健檢（部署後 / 更新後 / 疑似異常時）

```bash
desktop-harness selftest
```

注意事項：

- `selftest` 含**輕度 GUI 動作**（開 TextEdit、打字、滑鼠往返移動），會在螢幕上實際發生；執行前確認機器無人正在操作重要工作。
- `selftest` 會把 daemon 停掉再以 `--bg` 重啟做往返測試，結束時會停掉 daemon；若日常需要常駐 daemon，測完請再 `daemon start --bg`。
- 可見煙霧測試（人眼確認）：`desktop-harness demo`。

## daemon 專項健檢

```bash
desktop-harness daemon status
```

進階確認（socket 檔與 pid 檔存在、權限正確、無殘留）：

- 檔案權限應為 0600；若被放寬視為**安全事件**，立即 `daemon stop` 並依 [04-troubleshooting.md](./04-troubleshooting.md) 處置。
- daemon 停止後 socket 與 pid 檔應自動清除；若殘留即為異常。

## 審計記錄健檢

- 確認 audit log 檔案可寫入（`--doctor` 不覆蓋此項，可於測試中觸發一個動作後檢查檔案有新行）。
- 檢查檔案大小成長趨勢（無內建輪替，見 [06-monitoring-alerting.md](./06-monitoring-alerting.md)）。
