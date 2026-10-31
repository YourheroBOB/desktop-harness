# desktop-harness 操作手冊（docs/fmb 版）

> 依 v0.4.2 實際程式碼整理的安裝、執行、測試與除錯步驟。所有指令皆假設在 repo 根目錄執行。

## 1. 需求

- macOS（Sequoia+ 建議）
- Python 3.10+
- 終端機／agent host 取得 **Accessibility** 與 **Screen Recording** 權限

## 2. 安裝

### 2.1 一鍵安裝（建議）

```bash
cd /path/to/desktop-harness
chmod +x install.sh && ./install.sh
```

install.sh 實際做的事：
1. `python3 -m venv .venv`
2. 安裝三個 pyobjc framework 套件（Quartz / Cocoa / ApplicationServices）
3. `pip install -e . --no-deps`
4. 在 `~/.local/bin/desktop-harness` 產生 shim（指向本 clone 的 venv）
5. 若 `~/.grok` 存在，自動把 skill 寫到 `~/.grok/skills/desktop-harness/SKILL.md`
6. 執行一次 `--doctor`（失敗不中斷安裝）

### 2.2 手動安裝

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices
pip install -e . --no-deps

mkdir -p ~/.local/bin
ln -sf "$(pwd)/.venv/bin/desktop-harness" ~/.local/bin/desktop-harness
```

### 2.3 不安裝直接跑（開發用）

repo 根目錄有 dev launcher：

```bash
./desktop-harness --doctor    # 自動用 .venv（若有），否則 python3
```

### 2.4 授權（一次性）

```bash
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
```

- 勾選**執行 harness 的 host**（Terminal / Ghostty / iTerm / Grok）。
- Screen Recording 授予後**必須完整重啟該 host**才生效。

### 2.5 安裝 Grok skill

```bash
mkdir -p ~/.grok/skills/desktop-harness
desktop-harness skill > ~/.grok/skills/desktop-harness/SKILL.md
```

（`skill` 子命令從打包的 `desktop_harness/data/SKILL.md` 讀取，wheel 安裝也能用。）

### 2.6 更新（無靜默自動更新）

```bash
git pull
./install.sh          # 重建 venv + shim + skill
desktop-harness --version
```

## 3. 執行

### 3.1 環境檢查

```bash
desktop-harness --doctor     # pyobjc / Accessibility / Screen Recording / AX / 視窗列表
```

### 3.2 基本使用（heredoc 腳本）

```bash
desktop-harness <<'PY'
print(frontmost_app())
print(labels()[:15])
PY
```

```bash
desktop-harness <<'PY'
open_app("TextEdit")
click_text("Format")
PY
```

常用 helper 分類：
- 探索：`list_apps`、`list_windows`、`frontmost_app`
- 感知：`labels`、`button_labels`、`ax_snapshot`、`find`、`screenshot`
- 操作：`click_text`、`set_field`、`type_text`、`hotkey`、`key`
- 滑鼠：`mouse_pos`、`move_to`、`wiggle`、`click`、`click_frame`、`drag`、`scroll`
- 媒體：`media_transport`、`ensure_media_playing`
- Presence：`enable_agent_cursor`、`hide_agent_presence`
- Meta：`wait`、`wait_stable`、`verify`（任何改變畫面的動作後必呼叫並讀回截圖）

### 3.3 溫熱 daemon（多步任務建議）

```bash
desktop-harness daemon start --bg
desktop-harness daemon status
desktop-harness daemon stop
```

- daemon 起來後，後續 `desktop-harness <<'PY'` 會自動路由經 daemon（省 pyobjc 冷啟動）。
- `DH_NO_DAEMON=1` 強制走本機行程。
- daemon socket：`~/Library/Caches/desktop-harness/daemon.sock`（0600）；token：`~/.desktop-harness/daemon.token`（0600）。
- 第二次 `daemon start` 若已有活實例會明確拒絕並提示 `daemon stop`。

### 3.4 可見煙霧測試

```bash
desktop-harness demo   # 開 TextEdit、移滑鼠、打字、印 labels（人眼見證）
```

### 3.5 觀察迴圈（開發 presence／視覺類功能用）

```bash
./scripts/observe-demo.sh /tmp/dh-observe
# 產生多張密集截圖帧，讀多帧驗證 halo/橫幅在跨 app 點擊與閒置後仍在
```

注意（依 `docs/OBSERVE-LOOP.md`）：presence 類變更必須驗證「點擊落在別的 app + 之後數秒純閒置」後 overlay 仍在；單一靜態截圖不算數。不可用背景執行緒 pump AppKit（會 SIGABRT）—— 閒置等待用 `presence.keep_alive()` 分段處理。

### 3.6 實驗性語音（選用）

```bash
export XAI_API_KEY="…"   # 來自 console.x.ai；Grok Build 登入不算數
source .venv/bin/activate
pip install websockets sounddevice numpy
python scripts/voice_session.py --list-tools
python scripts/voice_session.py --dry-run          # 無 key 也可離線看工具
python scripts/voice_session.py --text "Open TextEdit"
```

無 key 且非 dry-run 時腳本會以明確訊息退出（exit 2）。麥克風串流尚未接線（scaffold 階段）。

## 4. 測試

### 4.1 selftest（非破壞性）

```bash
desktop-harness selftest
```

依 `selftest.py` 實際流程：
1. 先跑 `--doctor`（任一 FAIL 會計入失敗）
2. 核心測項：`list_apps`、`list_windows`、`frontmost_app`、`labels`、`mouse_pos`、滑鼠移動後復原（誤差 < 12px）、`screenshot`（> 1000 bytes）、`media_transport` API（`play` 必等於 `transport_play`）、`find_app` 精確匹配與 pid 路徑、`frame_on_screen` 過濾
3. 輕量 GUI：開 TextEdit + `cmd+n` + 打入時間戳 token（成功標準是 TextEdit 有視窗，不要求保持前景）
4. daemon：背景啟動 → `exec_via_daemon("print(1+1)")` 往返 → `quit`

回傳值：0 全過；1 有失敗（訊息會列 FAIL 項與例外）。

### 4.2 release 前檢查清單（RELEASE.md）

```bash
desktop-harness --doctor        # 全 PASS
desktop-harness selftest        # 全 PASS
desktop-harness demo            # 人眼確認滑鼠移動、TextEdit 打字
```

加上：確認 repo 無 secrets、skill 已安裝、CLI 在 PATH。

## 5. 除錯

### 5.1 常見失敗與處置

| 症狀 | 原因 | 處置 |
|------|------|------|
| doctor：pyobjc FAIL | venv 沒裝依賴 | `source .venv/bin/activate && pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices` |
| doctor：Accessibility FAIL | host 未授權 | 開 Privacy_Accessibility pane 勾選 host |
| doctor：Screen Recording FAIL（空截圖） | host 未授權，或授予後沒重啟 | 授權後**完整重啟**終端機／agent host |
| doctor：AX snapshot FAIL（0 節點） | Accessibility 未授 or 前景 app AX 為空 | 先確認 Accessibility；試換一個原生 app 當前景 |
| `click_text` 找不到目標 | label 不精確 / Electron app AX 稀疏 | 用 `labels()` 先看實際 label；`exact=True` 用於 Play/Pause 這類短詞；仍不行用 `screenshot(app=…)` 回落 |
| 誤點「Play all / Playing from」 | 寬鬆子字串匹配 | 一律 `click_text("Play", role="AXButton", exact=True)`，且先讀 `media_transport()` |
| 動作沒生效但沒例外 | AX 呼叫成功 ≠ 畫面如預期 | 呼叫 `verify("預期結果")` 並**讀回傳的截圖**再下結論 |
| 每次呼叫都慢 0.4s | socket 存在但 daemon 掛了 | `desktop-harness daemon stop`（會清 socket/pid）或手動刪 stale socket |
| daemon start 被拒 | 已有活實例 | `desktop-harness daemon status` 確認；`daemon stop` 後再啟 |
| PermissionError：refusing sensitive app | 敏感應用阻擋 | 正常行為。真的需要才 `DH_ALLOW_SENSITIVE=1`（單次、明白風險） |
| presence overlay 消失 | 跨 app 焦點切換/閒置時 run loop 沒被 pump | 跑 observe-demo 驗證；等待用 `keep_alive()`，**不要**開背景執行緒碰 AppKit |
| 開新 TextEdit 文件失敗 / 焦點被 agent host 搶走 | host 搶焦 | selftest 已內建 `open -a` + osascript activate 補強路徑；單獨腳本可仿照 |

### 5.2 診斷工具

```bash
desktop-harness --doctor                # 權限鏈逐項檢查
desktop-harness daemon status           # daemon 存活
ls -la ~/.desktop-harness/              # audit.jsonl、daemon.token
tail ~/.desktop-harness/audit.jsonl     # 近期 mutations 紀錄（activate/click_text/screenshot…）
```

### 5.3 環境變數速查

| 變數 | 用途 |
|------|------|
| `DH_NO_DAEMON=1` | 停用 daemon 路由（排查 daemon 問題時用） |
| `DH_MOUSE_INSTANT=1` | 滑鼠瞬移（縮短動畫干擾） |
| `DH_PRESENCE=0` | 關閉 overlay（排查 presence 是否干擾截圖） |
| `DH_ALLOW_SENSITIVE=1` | 解除敏感 app 阻擋（謹慎） |
| `DH_AUDIT_LOG` | 指定 audit log 路徑（測試時導到暫存檔） |
| `DH_SOCKET` / `DH_TOKEN_PATH` | 指定 daemon socket / token（多實例測試用） |

### 5.4 安全注意事項

- 這是真機、真滑鼠：送出訊息／貼文／付款／刪除／安全性設定／密碼相關動作前，agent **必須**停下來詢問使用者。
- 任意 Python 腳本以 host 權限執行（含可 `import subprocess`）；`DH_*` 閘門只包裹少數 helper —— 無人值守跑 agent 前請先審腳本。
- daemon 是本機特權端點；結束長 session 後建議 `desktop-harness daemon stop`；不要在多人共用機器上開著。
- 實體輸入永遠優先：人可以隨時搶回滑鼠。
