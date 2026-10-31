# desktop-harness 運作與除錯手冊（Runbook）

> 本手冊依據 `desktop-harness`（v0.4.2）實際原始碼與運作邏輯撰寫。涵蓋環境安裝、系統權限配置、日常執行操作、各項驗證測試劇本，以及深度疑難排解步驟。

---

## 1. 系統需求與前置準備

### 1.1 硬體與作業系統

- **作業系統**：macOS 14 (Sonoma) 或 macOS 15 (Sequoia) 以上（建議 Sequoia 以獲取較穩定的 AX 與權限行為）。
- **Python 直譯器**：Python 3.10 或以上版本（系統內建或 Homebrew 安裝皆可）。
- **硬體權限**：具備本機管理者權限（用以授權 macOS 輔助使用與螢幕錄製 TCC 隱私設定）。

### 1.2 必要的 macOS TCC 隱私權限

`desktop-harness` 需要以下兩項系統權限授權給**執行指令的宿主應用程式**（例如 Ghostty、Terminal、iTerm2、VS Code 或 Grok 宿主）：

1. **輔助使用（Accessibility）**：
   - 目的：讀取全系統 AX 語意樹，以及透過 `CGEventPost` 派送實體鍵鼠動作。
2. **螢幕錄製（Screen Recording）**：
   - 目的：於 AX 資訊空乏時截取視窗或全螢幕畫面（`CGWindowListCreateImage`）。
   - **注意**：macOS 規範在首次勾選「螢幕錄製」後，**必須完全退出並重啟該終端機／宿主應用**，授權才會正式生效。

---

## 2. 安裝與設定步驟

### 2.1 快速一鍵安裝（推薦路徑）

專案根目錄已提供 `install.sh` 自動化腳本：

```bash
git clone https://github.com/YourheroBOB/desktop-harness.git
cd desktop-harness
chmod +x install.sh && ./install.sh
```

`install.sh` 會自動執行：

1. 建立 `.venv` 虛擬環境並升級 pip。
2. 安裝核心 PyObjC 依賴（`Quartz`、`Cocoa`、`ApplicationServices`）。
3. 以可編輯模式（`pip install -e . --no-deps`）安裝本套件。
4. 在 `~/.local/bin/desktop-harness` 建立 PATH 轉接腳本。
5. 若偵測到 `~/.grok` 目錄，自動將 Agent Skill 安裝至 `~/.grok/skills/desktop-harness/SKILL.md`。
6. 自動執行一次 `--doctor` 檢驗權限現況。

完成後請確認 `~/.local/bin` 已加入 PATH：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 2.2 手動安裝與虛擬環境建置

```bash
cd desktop-harness

# 1. 建立並啟用虛擬環境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安裝相依 PyObjC 套件
pip install --upgrade pip
pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices

# 3. 安裝本套件（開發模式）
pip install -e . --no-deps

# 4. 建立 PATH 軟連結（選用）
mkdir -p ~/.local/bin
ln -sf "$(pwd)/.venv/bin/desktop-harness" ~/.local/bin/desktop-harness
```

### 2.3 註冊 Agent Skill

```bash
mkdir -p ~/.grok/skills/desktop-harness
desktop-harness skill > ~/.grok/skills/desktop-harness/SKILL.md
```

### 2.4 開啟系統權限面板

若 `--doctor` 提示權限缺失，可透過下列指令快速開啟系統偏好設定：

```bash
# 開啟輔助使用面板
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

# 開啟螢幕錄製面板
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
```

授權終端機後，**請將終端機視窗徹底關閉（Cmd+Q）並重新啟動**。

---

## 3. 日常執行與命令列操作

### 3.1 核心命令格式：Heredoc 執行

```bash
# 查看目前前景應用程式與前 15 個可見 UI 標籤
desktop-harness <<'PY'
print("目前前景：", frontmost_app())
print("畫面標籤：", labels()[:15])
PY
```

```bash
# 啟動應用程式並點擊按鈕
desktop-harness <<'PY'
open_app("TextEdit")
click_text("Format")  # 優先使用 AXPress
PY
```

```bash
# 真實滑鼠操控
desktop-harness <<'PY'
print("當前座標：", mouse_pos())
move_to(500, 350)
click(500, 350)
PY
```

### 3.2 溫熱常駐 Daemon 操作

為避免每次執行重複支付載入 Python 與 PyObjC 的冷啟動開銷（約 300–400ms），多步驟任務建議啟動背景 Daemon：

```bash
# 啟動 Daemon（背景模式）
desktop-harness daemon start --bg

# 查看 Daemon 運行狀態
desktop-harness daemon status

# 停止 Daemon
desktop-harness daemon stop
```

**Daemon 運作特性**：

- Daemon 執行中時，後續的 `desktop-harness <<'PY'` 會自動走本機 Unix Socket（`~/Library/Caches/desktop-harness/daemon.sock`）以 Token 認證通訊，延遲明顯下降。
- 若需強制繞過 Daemon 進行除錯：`DH_NO_DAEMON=1 desktop-harness <<'PY' ... PY`。

### 3.3 常用環境變數控制表

| 環境變數 | 預設值 | 功能說明 |
|----------|--------|----------|
| `DH_NO_DAEMON` | 未設定 | 設為 `1` 時強制在 CLI 行程內執行腳本，完全不嘗試連線 Daemon。 |
| `DH_MOUSE_INSTANT` | 未設定 | 設為 `1` 時滑鼠以 `CGWarp` 瞬移，關閉平滑移動動畫。 |
| `DH_PRESENCE` | `1` | 設為 `1` 顯示游標藍／紅光環及底部「Agent active」橫幅；設為 `0` 關閉。 |
| `DH_SAFE` | `1` | 啟用預設安全方針（Agent policy）。 |
| `DH_ALLOW_SENSITIVE` | 未設定 | 設為 `1` 時放行對敏感應用（密碼庫等）的操作與截圖（危險，謹慎使用）。 |
| `DH_AUDIT_LOG` | `~/.desktop-harness/audit.jsonl` | 覆寫稽核日誌存放路徑。 |
| `DH_SOCKET` | 快取目錄下 `daemon.sock` | 覆寫 Daemon Unix Socket 路徑（測試沙箱用）。 |
| `DH_TOKEN_PATH` | `~/.desktop-harness/daemon.token` | 覆寫 Daemon 鑑權 Token 路徑（測試沙箱用）。 |

---

## 4. 測試與驗證指南

每次變更程式碼或部署新機器時，請依序執行下列驗收鏈：

### 4.1 系統健康診斷（Doctor）

```bash
desktop-harness --doctor
```

- **檢查項目**：
  1. PyObjC 核心框架載入（Quartz、AppKit、ApplicationServices）。
  2. 輔助使用權限（`AXIsProcessTrusted()`）。
  3. 螢幕錄製權限（嘗試拍攝實體檔案並檢查大小 > 1000 bytes）。
  4. 當前前景應用的 AX 語意節點快照（節點數 > 0）。
  5. 螢幕可見視窗清單抓取。
- **預期輸出**：全數顯示 `[PASS]`，最後印出 `all clear — AX-first desktop control is ready.`。

### 4.2 非破壞性自測套件（Selftest）

```bash
desktop-harness selftest
```

- **檢查項目**：
  1. 執行 doctor 檢查。
  2. 核心 helper 導出驗證（`list_apps`、`frontmost_app`、`labels` 等）。
  3. 滑鼠座標讀取、小幅移動與原位復原。
  4. 視窗截圖檔產生與驗證。
  5. `media_transport` API 回傳結構完整性（`play == transport_play`）。
  6. `find_app` 精確／前綴排序與 PID 查詢路徑。
  7. `frame_on_screen` 螢幕邊界交叉判定。
  8. 啟動 TextEdit、發送熱鍵 Cmd+N、輸入文字煙霧測試。
  9. 背景啟動 Daemon 並驗證 Token 往返執行。
- **預期結果**：所有項目印出 `[PASS]`，結束狀態碼為 0。

### 4.3 可視化實體煙霧測試（Demo）

```bash
desktop-harness demo
```

- **行為**：
  - 螢幕游標出現半透明藍色光環，底部浮現霓虹提示橫幅。
  - 自動喚起 TextEdit 並建立新空白文件。
  - 游標移動至 TextEdit 視窗中央並執行擺動（wiggle）。
  - 自動輸入示範字串，印出 TextEdit 的 AX 標籤後隱藏視覺提示層。

### 4.4 密集視覺迴圈檢驗（Observe Loop）

當修改 `presence.py`、游標光環動畫或任何 UI 渲染元件時，單張截圖無法證明其在跨應用切換與閒置時的正確性；請執行專屬觀測腳本（輸出目錄請指向暫存目錄，例如 `"$TMPDIR/dh-observe"`）：

```bash
./scripts/observe-demo.sh "$TMPDIR/dh-observe"
```

該腳本會在動作期間連續拍攝多張高頻截圖（每 0.28 秒一張），供開發者檢視游標是否同步、橫幅是否閃爍，以及在焦點移出時是否仍正常渲染。

### 4.5 實驗性語音控制離線測試（Voice Dry-Run）

若需測試 `voice_tools.py` 的工具派送能力，在無 API 金鑰的情況下使用 `--dry-run` 離線模式（此模式不連線外部網路）：

```bash
python scripts/voice_session.py --dry-run
```

---

## 5. 常見問題與除錯手冊（Troubleshooting）

### 5.1 Doctor 報錯：`Screen Recording ... empty capture`

- **原因**：宿主終端機尚未取得螢幕錄製權限，或取得授權後未重啟終端機。
- **處置步驟**：
  1. 執行 `open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"`。
  2. 確認目前終端機開關為開啟；若已開啟，可嘗試關閉後重新勾選。
  3. **徹底關閉終端機（Cmd+Q）並重新啟動**。

### 5.2 Doctor 報錯：`Accessibility permission ... FAIL`

- **原因**：終端機或 Python 行程未列入輔助使用信任清單。
- **處置步驟**：
  1. 執行 `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"`。
  2. 將終端機應用程式加入並勾選。
  3. 若依然失敗，確認是否在 tmux / screen 內執行，改用原生終端視窗再驗證。

### 5.3 Daemon 無法連線、超時或殘留 Stale Socket

- **症狀**：執行指令卡頓約 0.4 秒，或 `daemon start` 回報已在運行但實際無法溝通。
- **排查與修復**：

```bash
# 1. 檢查是否有殘留常駐行程
ps aux | grep desktop_harness.daemon

# 2. 終止既有行程
pkill -f desktop_harness.daemon || true

# 3. 清理殘留的 socket 與 pid/token 檔
rm -f ~/Library/Caches/desktop-harness/daemon.sock
rm -f ~/Library/Caches/desktop-harness/daemon.pid
rm -f ~/.desktop-harness/daemon.token

# 4. 重新啟動 daemon
desktop-harness daemon start --bg
desktop-harness daemon status
```

### 5.4 遭遇 AppKit SIGABRT 崩潰（程序無預警中斷）

- **症狀**：執行含 GUI 邏輯的腳本時，Python 直譯器直接崩潰（`Fatal Python error: Aborted` / `SIGABRT`），無任何 Python Traceback。
- **原因**：違反 macOS AppKit 單一主執行緒約定（見 **ADR-0006**）。在背景 Thread 呼叫 AppKit / `NSWindow` 方法會被系統直接 abort。
- **處置原則**：
  - 檢查所有視窗調用，務必在主執行緒執行。
  - 若需在等待期間維持視窗渲染，請呼叫 `presence.keep_alive()` 進行主執行緒事件分片 pump，切勿建立背景執行緒更新 UI。

### 5.5 `PermissionError: refusing to control sensitive app`

- **症狀**：腳本拋出 `PermissionError`，拒絕操作指定應用或阻擋截圖。
- **原因**：觸發 `safety.py` 安全閘門（目標或前景 app 名稱／bundle 含 `1password`、`bitwarden`、`keychain` 等關鍵字）。
- **處置原則**：
  - 此為設計中的防護機制，避免 Agent 不慎讀取或竄改密碼庫內容。
  - 確認前景是否停留在密碼管理器或錢包軟體，切換至其他應用後重試。
  - 僅在明確知情且無風險的開發測試中，才以 `DH_ALLOW_SENSITIVE=1` 暫時解除封鎖。

### 5.6 `click_text` 找不到目標元素或點擊無反應

- **原因**：AX 樹未及時渲染、元素不在可視區域，或應用採非原生 Canvas/Web 繪製。
- **排查手段**：

```bash
# 1. 先輸出目前應用看得到的標籤
desktop-harness <<'PY'
print(labels()[:30])
PY

# 2. 檢視互動節點快照（限制 30 個）
desktop-harness <<'PY'
for node in ax_snapshot(max_nodes=30, interactive_only=True):
    print(node.get("role"), node.get("title"), node.get("frame"))
PY

# 3. 若 AX 樹完全為空，改走視窗截圖回落
desktop-harness <<'PY'
p = screenshot(app="目標應用名稱")
print("截圖落地於：", p)
PY
```

### 5.7 檢視稽核日誌（Audit Log）

所有啟動應用、點擊文字、截圖與媒體操作皆會記錄於本機稽核日誌：

```bash
tail -n 20 ~/.desktop-harness/audit.jsonl
```

每筆記錄包含時間戳記、事件類型與目標參數（基於安全考量，文字輸入內容不會被記錄）。
