# desktop-harness 分階段相依升級計畫

**狀態：** 提案，未實際升級。  
以下「變更」指的是未來實作分支的建議變更；本任務只新增此文件，不修改任何現有檔案。

---

## Phase 0 — 基線與環境 snapshot

### 變更
- 不做任何產品或相依變更。
- 在目標 Mac 上記錄：
  - `python3 --version`
  - `python3 -m pip --version`
  - `python3 -m pip check`
  - `sw_vers`
  - `uname -m`
  - `desktop-harness --version`
  - `desktop-harness --doctor`
  - `desktop-harness daemon status`
  - 三個 pyobjc framework 與 hatchling 的 exact installed version
- 將結果寫入 PR 描述或本地暫存報告，不提交版本鎖檔。

### 相容性風險
- 低。`--doctor` 可能產生一張截圖以驗證 Screen Recording，但屬只讀診斷。
- 不應在此階段執行 `demo` 或會改變滑鼠／視窗的操作。

### 驗證方式
- 確認 `pip check` 無 broken dependency。
- 確認 `desktop-harness --doctor` 的 Accessibility／Screen Recording 狀態可作為升級前基線。
- 確認目前 daemon 狀態，以便後續還原。

### 回滾方式
- 無需回滾；本階段不修改系統或 repo。

---

## Phase 1 — 打包衛生與 preflight

### 變更
未來實作分支可考慮：

- 在 `pyproject.toml` 為三個 pyobjc 相依加入保守版本下限，下限以 Phase 0 實測版本為錨點。
- 補 build-system 的 hatchling 版本下限或區間，避免任意漂移。
- 宣告 license metadata。
- 新增 `[project.optional-dependencies]` 的 `voice` extras，包含 `websockets`、`sounddevice`、`numpy`。
- 新增 pytest 基本設定，作為後續自動化測試地基。
- 在安裝腳本或 launcher 增加 preflight：macOS、`python3 >= 3.10`、`.venv` 可用性。

### 相容性風險
- 加入版本下限可能排除少數老舊環境。
- preflight 可能讓非 macOS 平台提前失敗，但 desktop-harness 本來就只支援 macOS。
- license metadata 與 extras 不影響 runtime，但可能影響 build。

### 驗證方式
- 在暫存 venv 中離線安裝目前 wheel 或 editable package，執行：
  - `python -m pip check`
  - `python -c "import desktop_harness"`
  - `desktop-harness --version`
- 建置 wheel／sdist，檢查：
  - entry point 存在
  - `desktop_harness/data/SKILL.md` 有被打包
  - license metadata 出現
- 不連線 PyPI 或正式服務。

### 回滾方式
- 直接 revert Phase 1 commit。
- 重新建置並安裝前一版 wheel。
- 不需要迁移使用者資料。

---

## Phase 2 — Python 支援矩陣與語言版本決策準備

### 變更
- 暫不提高 `requires-python`。
- 在本機或暫存目錄建立 Python 3.10、3.11、3.12 的驗證矩陣；若環境有 3.13 也可列為實驗項。
- 記錄每個 Python 版本可安裝的 pyobjc / hatchling 版本。
- 文件化支援矩陣，但不强制所有使用者升級 Python。

### 相容性風險
- pyobjc 最新版可能不再支援 Python 3.10。
- 新版 Python 可能有 deprecated API 或 asyncio 行為差異。
- Homebrew Python 與 Xcode CLT Python 的 venv 行為不同。

### 驗證方式
- 使用 `tempfile` / `tmp_path` 建立暫存 venv。
- 在每個 venv 中：
  - `python -c "import desktop_harness"`
  - `desktop-harness --version`
  - `desktop-harness --doctor`
- daemon 相關驗證使用暫存：
  - `DH_SOCKET=<tmp>/daemon.sock`
  - `DH_TOKEN_PATH=<tmp>/daemon.token`
  - `DH_AUDIT_LOG=<tmp>/audit.jsonl`
  - `DH_NO_DAEMON=1` 用於 in-process 路徑
- 不連線 PyPI；如環境無法離線取得 wheel，則記錄為待確認，不可連正式服務。

### 回滾方式
- 刪除暫存 venv。
- 不修改 `requires-python`，因此無產品回滾成本。

---

## Phase 3 — pyobjc 核心相依升級

### 變更
一次只處理一個主題，建議順序：

1. `pyobjc-framework-ApplicationServices`
2. `pyobjc-framework-Quartz`
3. `pyobjc-framework-Cocoa`

每個 PR：

- 只升級一個 framework，必要時同步其 pyobjc transitive dependency。
- 以「仍相容於 Python 3.10 與目標 macOS」為限制，選擇最小安全升級，不盲目追最新。
- 在 PR 記錄 old exact version → new exact version。
- 重跑 install 或 venv 重建。

### 相容性風險
- AX API、截圖、CGEvent、AppKit overlay 行為可能變化。
- pyobjc 新版本可能调整 deprecated binding。
- warm daemon 可能仍載入舊模組。
- presence overlay 對 main-thread 約束敏感，不可用背景執行緒更新 UI。

### 驗證方式
- 暫存 venv：
  - `python -m pip check`
  - import 三個 framework
  - `python -c "import desktop_harness"`
- 主機非破壞驗證：
  - `desktop-harness --doctor`
  - `desktop-harness selftest`
  - 針對性驗證 `list_windows`、`frontmost_app`、`labels`、`find_app`、`ax_snapshot`、`screenshot`
- 滑鼠復原驗證：
  - 記錄 `mouse_pos()`
  - 執行受控 `move_to`
  - 驗證可回到原位或明確失敗
- 不執行固定座標 `click(520,420)` 之類可能誤觸開發者畫面的腳本。
- 不連線任何正式服務。

### 回滾方式
- 在 venv 中安裝旧 exact 版本：
  - `python -m pip install pyobjc-framework-Quartz==<OLD_EXACT>`
  - 依此處理 Cocoa／ApplicationServices
- revert `pyproject.toml` 或 constraints 变更。
- 停止並重启 daemon，確認沒有 stale socket／pid。

---

## Phase 4 — warm daemon 相容性與安全屬性驗證

### 變更
- 在 Phase 3 後重启 daemon 並驗證協定。
- 不修改正式使用者 daemon；全部使用暫存路徑。

### 相容性風險
- CLI 與 daemon 版本漂移。
- NDJSON 協定迴歸。
- socket／token 權限錯誤。
- daemon 異常終止後留下 stale socket／pid。

### 驗證方式
使用暫存環境：

```bash
export DH_SOCKET=<tmp_path>/daemon.sock
export DH_TOKEN_PATH=<tmp_path>/daemon.token
export DH_AUDIT_LOG=<tmp_path>/audit.jsonl
```

驗證：

- `daemon start`
- `daemon status`
- `ping` 成功
- 帶正確 token 的 `exec` 成功
- 帶假 token `FAKE_VALUE_FOR_TEST` 的 `exec` 被拒絕
- socket 與 token 檔案為 0600
- 輸出中不出現 token 值
- `daemon stop` 後暫存 socket／pid 清理符合預期

### 回滾方式
- 停止暫存 daemon。
- 刪除暫存目錄。
- 若 Phase 0 記錄到使用者原本有 daemon，升级完成後手動重启原 daemon。

---

## Phase 5 — 實驗性 voice 相依 extras

### 變更
- 將 `websockets`、`sounddevice`、`numpy` 宣告為 optional `voice` extras。
- 不加入核心 dependencies。
- 文件明確：
  - 金鑰只放環境變數或 Keychain
  - 不可寫入命令列、repo、context vault
  - 測試使用 `FAKE_VALUE_FOR_TEST`

### 相容性風險
- `sounddevice`、`numpy` binary wheel 可能不相較於某些 Python/macOS 組合。
- 麥克風權限與語音內容隱私風險。
- 現行 `--dry-run` 可能仍執行真實 GUI；未修正前不應作為自動 gate。

### 驗證方式
- 暫存 venv 安裝 voice extras。
- 僅離線驗證：
  - import `websockets`
  - import `sounddevice`
  - import `numpy`
  - 工具 schema 可載入
- voice session 一律使用本地 mock WebSocket；若使用 `--dry-run`，必須先確認 dry-run 不會執行真實 GUI 或連網。
- 不連線 `wss://api.x.ai/v1/realtime`。

### 回滾方式
- 不安裝 voice extras；核心安裝路径不受影响。
- revert extras 宣告。
- 刪除暫存 venv。

---

## Phase 6 — 建置系統與可重現打包

### 變更
- 在 `build-system.requires` 中加入 hatchling 版本區間。
- 以暫存 venv 建置 wheel／sdist。
- 驗證 metadata 與 package data。

### 相容性風險
- hatchling 新版本可能改變 wheel metadata。
- `force-include` 行為可能影響 `SKILL.md` 打包。
- build isolation 可能抓取不同 backend 版本。

### 驗證方式
- 使用暫存 venv與已安裝 hatchling：
  - `python -m build --no-isolation`
  或
  - `python -m pip wheel . --no-deps --no-build-isolation`
- 檢查 wheel：
  - 包含 `desktop_harness/`
  - 包含 `desktop_harness/data/SKILL.md`
  - 包含正確 entry point
  - 包含 license metadata
- 安裝 wheel 到另一個暫存 venv：
  - `desktop-harness --version`
  - `python -c "import desktop_harness"`
- 不連線 PyPI 或正式服務。

### 回滾方式
- 還原 hatchling 版本區間。
- 使用舊 backend 重建 wheel。
- 不安裝新 wheel 到正式環境。

---

## Phase 7 — Canary 發佈、監控與文件同步

### 變更
- 在通過前述 Gate 後，建立 canary tag 或 canary 分支。
- 不啟用靜默自動更新。
- 文件更新只能在對應實作分支處理；本任務不修改現有文件。

### 相容性風險
- 使用者機器上舊 daemon 仍在運行。
- Screen Recording 權限可能需重启 host app。
- CLI 與 daemon 版本短暫不一致。
- 安裝來源 URL 文件不一致，可能造成 clone 混淆。

### 驗證方式
- 在一台 canary Mac：
  - 以乾淨暫存 clone 安裝
  - `desktop-harness --doctor`
  - `desktop-harness selftest`
  - `desktop-harness demo`，但需人工確認 TextEdit 存在並全程監看
  - `desktop-harness daemon start/status/stop`
- 不自動執行 `check-update`；如手動執行，應視為使用者主動連線，不寫入自動測試。
- 不連線正式 voice 服務。

### 回滾方式
- 停止 daemon。
- 還原上一個 tag 或 commit。
- 在 venv 重新安裝舊 exact pyobjc 版本。
- 若 daemon stop 後留下 stale socket／pid，於 stop 成功後清理。
- 重新執行 `--doctor` 與 `selftest` 確認回到可用狀態。

---

## 升級 Gate 總覽

| Gate | 完成條件 |
|------|----------|
| G0 | Phase 0 基線已完成，舊版本與環境事實可追溯 |
| G1 | Phase 1 離線打包、`pip check`、import、entry point 通過 |
| G2 | Phase 2 Python 支援矩陣已有記錄，3.10 仍可用 |
| G3 | Phase 3 每個 pyobjc 升級都有實機非破壞驗證 |
| G4 | Phase 4 暫存 daemon 協定與 0600 權限驗證通過 |
| G5 | Phase 5 voice extras 離線 mock 驗證通過 |
| G6 | Phase 6 wheel 可安裝、`SKILL.md` 與 metadata 正確 |
| G7 | Phase 7 canary 人工驗證通過，且有明確回滾路徑 |

---

## 明確不做

- 不一次升級所有核心相依。
- 不為了追新而提高 Python/macOS 最低需求。
- 不把 voice 實驗變成核心安装路径。
- 不加入靜默自動更新。
- 不修改 `.github/workflows` 或 secrets。
- 不在文件中放入任何真實金鑰、token、密碼或個資。
