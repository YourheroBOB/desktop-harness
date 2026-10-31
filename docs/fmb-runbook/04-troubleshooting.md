# 常見故障：症狀 → 診斷 → 處置

> 原則：先跑 `desktop-harness --doctor`，修好**第一個 FAIL** 再看後面——後續失敗常是連鎖反應。

## F1 權限失效（doctor：Accessibility FAIL）

- **症狀**：`--doctor` 顯示 Accessibility FAIL；`ax_snapshot` / `labels` 回空或噴例外；滑鼠不動、打字無效。
- **診斷**：Accessibility 未授予「實際執行 host」，或 host 更新後權限被重置。
- **處置**：
  1. 開系統設定 Accessibility 面板，確認勾選的是 Terminal / Ghostty / iTerm / Grok host 本身。
  2. 若已勾選仍 FAIL：把該 host 的勾選**取消再重勾**（toggling 常見有效），必要時重啟 host。
  3. 重跑 `--doctor` 確認 PASS。

## F2 螢幕錄製權限（doctor：Screen Recording FAIL / 空截圖）

- **症狀**：doctor 顯示 capture 為 0 bytes 或 FAIL；`screenshot()` 例外。
- **診斷**：Screen Recording 未授予，或授予後**未完全重啟 host**（最常見原因）。
- **處置**：授予後**完整退出並重啟**執行 host（⌘Q，不是關視窗），再重跑 `--doctor`。

## F3 AX 樹為空 / 稀疏（Electron、自繪 UI）

- **症狀**：`labels()` 回空或很少、`click_text` 找不到目標。
- **診斷**：目標是 Electron／canvas／遊戲類 App，AX 樹本來就稀疏（已知限制，非故障）。
- **處置**：改用 `screenshot()` fallback + 座標點擊；確認目標 App 在前景（座標點擊需要目標為 frontmost）。若該 App 常用，考慮請 agent 優先走 shell / API 路徑。

## F4 daemon 連不上 / CLI 每次呼叫延遲

- **症狀**：`daemon status` 顯示未運行但 socket 檔存在；每次 CLI 呼叫前都卡一段時間才 fallback 到 in-process。
- **診斷**：daemon 掛掉但殘留 socket / pid 檔；或 daemon 程序存活但無回應。
- **處置**：
  1. `desktop-harness daemon stop`（清理）；若無回應，直接刪殘留的 socket 與 pid 檔。
  2. `desktop-harness daemon start --bg`，然後 `daemon status` 確認。
  3. 排查期間可用 `DH_NO_DAEMON`（設為啟用）強制 in-process 維持服務。

## F5 daemon 拒絕請求（unauthorized）

- **症狀**：daemon 回 `unauthorized (bad or missing token)`。
- **診斷**：token 檔被刪/換路徑、權限被改，或客戶端未帶 token。
- **處置**：
  1. `daemon stop` → `daemon start --bg`（啟動時會重寫 token）。
  2. 若使用了路徑覆寫變數，確認客戶端與 daemon 端設定一致。
  3. 若**權限不是 0600** 或 token 檔出現非預期內容，視為安全事件：停 daemon、輪換 token（重啟即重寫）、檢視 audit log。

## F6 敏感 App 被擋（PermissionError: refusing to control sensitive app）

- **症狀**：`open_app` / `activate` / 變更動作 / 截圖對密碼管理器類 App 拋 PermissionError。
- **診斷**：這是**預設安全行為**，不是故障。App 名稱或 bundle id 命中敏感清單（含「wallet」「bank」等較寬的字串，可能誤判）。
- **處置**：
  - 若為誤判且任務確有必要：在**單人、有人監看**的前提下暫時設定 `DH_ALLOW_SENSITIVE` 啟用，任務結束立即還原。
  - 若屬誤判但無法確認：保守做法是**不**開啟，改由人類手動操作該 App。

## F7 滑鼠/焦點被搶、動作打錯 App

- **症狀**：點擊落在錯的視窗、TextEdit 測試中焦點一直跳回 agent host。
- **診斷**：agent host 搶焦點是已知環境行為；座標動作要求目標 App frontmost。
- **處置**：動作前先 `activate`（helper 內建確認迴圈）；必要時用 AX 路徑（`click_text`）取代座標；任務間隔請人類暫停 agent host 前台活動。

## F8 媒體誤操作（重複播放/暫停/跳歌）

- **症狀**：agent「按播放」後發生暫停↔播放反覆或跳到別首歌。
- **診斷**：參見 repo 的 postmortem：Space 是 toggle、loose match 撈到「Play all」「Playing from」、成功後仍重試。
- **處置**：規範 agent 行為（skill 內已載明）：先 `media_transport()` 讀狀態 → 只做一次動作 → `ensure_media_playing()` 或 `exact=True` 的 `click_text` → 驗證即停。人類端可隨時實體搶回滑鼠中斷。

## F9 版本不一致 / 更新後異常

- **症狀**：`--version` 與預期不符、行為與文件描述對不上、更新後 agent helpers 沒生效。
- **診斷**：更新時未重跑 `install.sh`、shim 指到舊 venv、或 daemon 未重啟（helpers 只在 daemon 啟動時載入一次）。
- **處置**：`daemon stop` → `./install.sh` → `--doctor` / `selftest` → `daemon start --bg`。仍異常則依 [05-rollback.md](./05-rollback.md) 回滾。

## F10 audit log 無限成長

- **症狀**：`audit.jsonl` 持續變大、占磁碟。
- **診斷**：無內建輪替（已知限制）。
- **處置**：見 [06-monitoring-alerting.md](./06-monitoring-alerting.md) 的輪替建議；輪替前先確認無進行中調查需求。

## 升級通則

任何處置後，最後一律重跑：

```bash
desktop-harness --doctor && desktop-harness selftest
```

仍無法解決 → 收集 `--doctor` 與 `selftest` 輸出（**不含任何密碼/個資畫面內容**）開 issue。
