# desktop-harness 架構說明（docs/fmb 版）

> 本文件基於 repo `YourheroBOB/desktop-harness`（版本 0.4.2）的實際程式碼撰寫，僅供中文讀者快速理解系統。原始英文設計文件請參考 `DESIGN.md`、`HOW_IT_WORKS.md`。

## 1. 專案定位

desktop-harness 是一個 **macOS 本機 CLI + agent skill**，讓 coding agent（主要為 Grok Build，亦可為任何能執行 shell 的 agent）控制真實的 Mac 桌面：

- **看（眼睛）**：優先讀取 macOS Accessibility（AX）樹，結構化文字、毫秒級；AX 不足時才退回視窗截圖。
- **動（手）**：透過 `CGEvent` / `CGWarpMouseCursorPosition` 驅動**真實的**系統滑鼠與鍵盤，輔以 AX 元素動作（`AXPress`、set value）。
- **不是 MCP server**：agent 直接以 `desktop-harness <<'PY' … PY` 的 heredoc 形式餵入 Python 程式碼執行。

## 2. 模組圖

```
agent（Grok Build / Claude Code / Codex CLI / 任何 shell）
  │  desktop-harness <<'PY' … PY
  ▼
run.py ── CLI 進入點（desktop_harness.run:main）
  │（判斷 daemon 是否可用：DH_NO_DAEMON、socket ping 0.4s）
  ├── 就地執行 _exec_local ────────┐
  └── 經 daemon 執行 exec_via_daemon ─┐
                                     ▼
                              helpers.py ── 公開 API 表層（namespace()）
                    ┌─────────────┼──────────────┬─────────────┐
                    ▼             ▼              ▼             ▼
               windows.py      ax.py         capture.py     input.py
             應用/視窗列舉   AX 樹/尋找/    視窗/畫面截圖   CGEvent 滑鼠
             前景偵測/啟動   按下/設值      (PNG 回落)     鍵盤/拖曳/捲動
                    │             │
                    └── safety.py ┘（敏感應用阻擋、audit log）
                    │
              presence.py（agent cursor 藍/紅光環 + 「hands off」橫幅）
                    │
              daemon.py（溫熱常駐：Unix socket 0600 + token 驗證）
                    │
   ┌────────────────┴───────────────────┐
   ▼                                    ▼
admin.py（--doctor 權限健檢）   selftest.py（非破壞性自測）
demo.py（可見煙霧測試：開 TextEdit、移滑鼠、打字）
voice_tools.py（Grok Voice 工具 schema + 本地執行器，實驗性）
```

### 各模組職責（依實際檔案）

| 模組 | 職責 |
|------|------|
| `src/desktop_harness/run.py` | CLI 入口：解析 `--doctor`、`selftest`、`demo`、`skill`、`daemon start/stop/status`、`check-update` 等子命令；決定腳本走本機行程或 daemon。 |
| `helpers.py` | agent 可呼叫的完整 helper 表面（`open_app`、`click_text`、`labels`、`set_field`、`media_transport`、`ensure_media_playing`、`verify`、`wait`、`wait_stable` 等），並組出腳本命名空間（含 `agent-workspace/agent_helpers.py`）。 |
| `windows.py` | `list_apps` / `list_windows`（CGWindowList）/ `frontmost_app`（NSWorkspace）/ `find_app`（精確 → 前綴 → 最短子字串 → bundle id）/ `activate`（`open -a` 備援、已前景則跳過、事後確認焦點）。 |
| `ax.py` | AX 樹走訪與快照（`ax_snapshot`、`find`、`labels`）、`AXPress`、`AXSetAttributeValue`、座標換算、畫面上 frame 過濾（`frame_on_screen`）。 |
| `capture.py` | `CGWindowListCreateImage` 視窗／主畫面截圖 → PNG；檔名含 pid + `time_ns()` 避免並發覆蓋；截圖前跑敏感應用檢查。 |
| `input.py` | 真實 HID：`CGWarpMouseCursorPosition` + `CGEventPost`（點擊、拖曳、捲動、鍵盤、hotkey）。 |
| `safety.py` | 敏感應用（密碼管理器類）名稱/bundle 子字串阻擋（`DH_ALLOW_SENSITIVE` 可覆寫）；前景敏感應用時阻擋 mutating 動作與截圖；audit log 寫 `~/.desktop-harness/audit.jsonl`。 |
| `daemon.py` | 溫熱常駐：NDJSON-over-Unix-socket；socket 與 token 檔皆 0600；PID 檔單一實例檢查；`op: ping/quit/exec`，exec 前必須驗 token。 |
| `presence.py` | 視覺提示：單一系統游標 + 藍色光環（移動）、紅色短閃（點擊）、底部「Agent controlling」橫幅；`keep_alive()` 分段 pump 主執行緒（AppKit 不可跨執行緒操作視窗，背景執行緒曾導致 SIGABRT）。 |
| `admin.py` | `--doctor`：pyobjc import、Accessibility（`AXIsProcessTrusted`）、Screen Recording（實拍一張並驗檔案大小）、前景 app AX 快照節點數、視窗列表。 |
| `selftest.py` | 非破壞自測：先跑 doctor，再測核心 helper、滑鼠移動復原、截圖、`media_transport` API、`find_app` 排序（含 pid 路徑）、`frame_on_screen`、TextEdit 開啟＋打字、daemon 背景啟動＋exec 往返。 |
| `demo.py` | 可見煙霧測試：開 TextEdit、`cmd+n`、移滑鼠進視窗、打字、印 labels、收起 presence。 |
| `voice_tools.py` / `scripts/voice_session.py` | 實驗性語音控制：xAI Realtime WebSocket（`grok-voice-think-fast-2.0`）function calling → 本地執行 harness 工具。需 `XAI_API_KEY`（與 Grok Build 登入不同）。 |

## 3. 資料流

### 3.1 一次典型的 agent 呼叫

```
agent 下達：
  desktop-harness <<'PY'
  open_app("TextEdit"); click_text("Format")
  PY
        │
        ▼
run.main → 讀 stdin 腳本
        │
        ├─ daemon.is_running()（socket ping，timeout 0.4s）
        │     ├─ 是 → daemon.client_request({op:"exec", code, token})
        │     │        → 已載入 pyobjc 的常駐行程 exec() → 回 {ok, stdout, stderr}
        │     └─ 否 → 本機行程：組 namespace()（helpers + agent-workspace）→ exec()
        ▼
helpers.open_app → windows.activate
        │  safety.check_app_allowed（敏感名稱 → PermissionError）
        │  find_app（精確/前綴/子字串/pid）
        │  NSRunningApplication.activateWithOptions_ / open -a 備援
        │  輪詢確認成為前景（最多 1.2s）→ safety.audit("activate")
        ▼
helpers.click_text("Format")
        │  ax.find → 走訪 AX 樹找最佳匹配（exact > 短字詞分數）
        │  有 AXPress → 直接按（不需座標）
        │  否則 → input.click(frame 中心)（CGWarp + CGEventPost）
        │  presence：移動顯示藍環、點擊紅閃
        │  safety.audit("click_text")
        ▼
stdout 回給 agent
```

### 3.2 感知優先順序（efficiency contract）

1. **Shell/API** 優先（不是真 GUI 任務就不進 harness）
2. **AX 樹**（`labels` / `ax_snapshot` / `find`）— 主要眼睛
3. **`AXPress` / set value** 元素動作優先於座標點擊
4. **視窗截圖**（`capture.screenshot`）— 僅在 AX 為空（Electron、canvas、遊戲）時使用
5. **OCR/vision** — agent 端最後手段；harness 不內建 vision loop

### 3.3 媒體控制資料流（教訓驅動）

`media_transport()` 讀取播放器 AX 狀態 → 回 `{state: playing|paused|unknown, transport_play, row_play, play}` → `ensure_media_playing()` 只在**尚未播放**時按一次精確 Play → 再讀一次狀態確認。絕不連按 Space（會 toggle 暫停）。背景：`docs/POSTMORTEM-media-play.md`。

### 3.4 環境變數（資料流的開關）

| 變數 | 效果 |
|------|------|
| `DH_NO_DAEMON=1` | 一律本機行程，不 ping daemon |
| `DH_MOUSE_INSTANT=1` | 滑鼠瞬移不動畫 |
| `DH_PRESENCE=1`（預設） | 光環 + 橫幅開啟；`=0` 關閉 |
| `DH_SAFE=1`（預設） | 安全政策（agent 導向） |
| `DH_ALLOW_SENSITIVE=1` | 解除敏感應用阻擋（勿隨意開） |
| `DH_AUDIT_LOG` | 覆寫 audit log 路徑 |
| `DH_SOCKET` / `DH_TOKEN_PATH` | 覆寫 daemon socket / token 路徑 |

## 4. 外部相依

### 4.1 Python 套件（pyproject.toml）

| 套件 | 用途 |
|------|------|
| `pyobjc-framework-Quartz` | CGWindowList、CGEvent、螢幕邊界、截圖 |
| `pyobjc-framework-Cocoa` | NSWorkspace、NSRunningApplication、NSBitmapImageRep（PNG 編碼）、presence 的 AppKit overlay |
| `pyobjc-framework-ApplicationServices` | `AXIsProcessTrusted`、AX API |

建置系統：hatchling；wheel 以 force-include 把 `SKILL.md` 打包成 `desktop_harness/data/SKILL.md`（`desktop-harness skill` 子命令輸出用）。

### 4.2 macOS 系統相依

| 相依 | 用途 | 對應權限 |
|------|------|----------|
| Accessibility API（AXUIElement） | 讀 UI 樹、AXPress、set value | **Accessibility**（隱私權設定） |
| CGEvent / CGWarpMouseCursorPosition | 真實滑鼠鍵盤注入 | **Accessibility** |
| CGWindowListCreateImage | 視窗／畫面截圖 | **Screen Recording**（授予後需重啟 host app） |
| `open -a`、`osascript`（subprocess） | 應用啟動／啟用的備援路徑 | 無特殊權限 |
| `screencapture` | observe loop 的密集取帧（`scripts/observe-demo.sh`） | Screen Recording |

最低 Python 3.10；macOS Sequoia+ 建議。

### 4.3 檔案系統足跡（執行期）

| 路徑 | 內容 | 權限 |
|------|------|------|
| `~/.desktop-harness/audit.jsonl` | key mutations 審計紀錄 | — |
| `~/.desktop-harness/daemon.token` | daemon 驗證 token | 0600 |
| `~/Library/Caches/desktop-harness/daemon.sock` | daemon Unix socket | 0600 |
| `~/Library/Caches/desktop-harness/daemon.pid` | 單一實例 PID 檔 | 0600 |
| `$TMPDIR/desktop-harness/capture-<pid>-<ns>.png` | 截圖輸出（每呼叫唯一檔名） | — |
| `~/.grok/skills/desktop-harness/SKILL.md` | install.sh 自動註冊的 Grok skill（若 `~/.grok` 存在） | — |
| `agent-workspace/agent_helpers.py` | agent 自訂 helper（自動載入每個腳本命名空間） | — |

### 4.4 網路相依

- **核心功能零網路**：所有控制皆本機。
- 唯一例外是**實驗性語音**（`scripts/voice_session.py`）連 `wss://api.x.ai/v1/realtime`，需 `XAI_API_KEY`（console.x.ai）；無 key 時腳本明確退出、`--dry-run` 可離線檢視工具。
- `desktop-harness check-update` 只與 GitHub main 比對版本（選用）。

## 5. 已知限制（誠實條目）

- 前景 HID 為主：控制目標 app 時可能搶焦點；真正背景不搶焦控制尚未實作。
- Electron／部分 web app AX 稀疏 → 需截圖回落。
- presence overlay 在多螢幕的座標轉換未保證。
- daemon 是「本機特權 exec 端點」：能連上 socket 並持 token 的同 UID 行程可執行任意 Python；不應在多人共用機器上開著。
- 任意 `exec` 是產品特性：`DH_*` 閘門只包裹少數 helper，腳本本身可 `import subprocess` 繞過 —— 這是有意的彈性，風險由使用者承擔（見 SECURITY.md）。
