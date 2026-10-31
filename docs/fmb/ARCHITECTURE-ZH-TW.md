# desktop-harness 架構說明（docs/fmb 版）

> 本文件基於 repo `YourheroBOB/desktop-harness`（版本 v0.4.2）之原始碼、ADR 決策紀錄與架構審查報告撰寫。旨在提供完整深入的模組架構圖、執行期資料流、安全閘門機制與外部系統相依說明。

---

## 1. 專案定位與核心設計哲學

desktop-harness 是一個專為 macOS 設計的 **本機 CLI 工具 + Agent Skill**，主要作為 coding agent（首要支援 Grok Build，亦全面相容 Claude Code、Codex CLI 或任何具備 shell 執行權限的 agent）操控 Mac 實體桌面的手與眼。

### 核心原則（Efficiency Contract）

1. **Shell / API 優先**：若任務可透過命令列、檔案系統或 HTTP API 完成，絕不啟動 GUI 自動化。
2. **AX（輔助功能樹）優先於像素**：優先解析 macOS Accessibility API 產生的結構化語意節點（數十毫秒、零視覺 Token 成本），視窗截圖僅作 AX 樹為空或 custom canvas 時的回落（Fallback）。
3. **元素動作優先於實體座標**：優先使用 `AXPress` 或 `AXSetAttributeValue` 直接觸發元件，只有在無對應 AX 動作時才退回滑鼠座標點擊。
4. **絕不預設 Vision Loop**：不採取傳統「截圖 → 傳送模型 → 猜座標 → 點擊」的高延遲、高成本循環。
5. **變更後強制驗證（Verify after Mutation）**：動作無例外拋出僅代表 API 呼叫成功，不代表畫面狀態改變；改變畫面的操作後須由 agent 讀取驗證截圖確認畫面符合預期。
6. **本機特權邊界與人身覆蓋**：驅動實體系統游標（HID），人類隨時可透過物理滑鼠搶回控制權；敏感應用程式於執行期阻擋變更與截圖。

---

## 2. 模組架構圖

```
┌────────────────────────────────────────────────────────────────────────┐
│            Agent 主控層（Grok Build / Claude Code / Shell）             │
│                 指令格式：desktop-harness <<'PY' ... PY                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ stdin Python 腳本
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ run.py — CLI 進入點（desktop_harness.run:main）                         │
│   ├─ 子命令：--doctor | selftest | demo | skill | daemon | check-update│
│   └─ 執行路由策略：                                                    │
│        ├─ DH_NO_DAEMON=1 或 daemon 未啟動 ──► _exec_local (In-Process) │
│        └─ daemon.sock 存在且 ping 通 ────────► exec_via_daemon (Socket)│
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │ 本地直接呼叫                    │ Unix Socket (0600) + Token
                    ▼                                ▼
┌───────────────────────────────────┐    ┌───────────────────────────────┐
│ In-Process 執行空間               │    │ daemon.py（溫熱常駐行程）     │
│  - 組裝 namespace() 命名空間      │    │  - 預載 PyObjC 框架           │
│  - 即時 exec(code, ns, ns)        │    │  - NDJSON 協定 (ping/quit/exec)│
└───────────────────┬───────────────┘    │  - 0600 Token 鑑權驗證        │
                    │                    └───────────────┬───────────────┘
                    └───────────────────┬────────────────┘
                                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ helpers.py — 公開 API 表層（namespace 導出函式庫）                    │
│   含 agent-workspace/agent_helpers.py 動態擴充模組                     │
└───────┬───────────────┬────────────────┬───────────────┬───────────────┘
        │               │                │               │
        ▼               ▼                ▼               ▼
┌──────────────┐┌──────────────┐┌────────────────┐┌──────────────┐
│  windows.py  ││    ax.py     ││   capture.py   ││   input.py   │
│  視窗與應用  ││ Accessibility││   截圖與圖像   ││  實體 HID 鍵鼠│
│ 探索、啟動、 ││ 樹走訪、過濾 ││ CGWindowList   ││ CGWarpMouse /│
│ 焦點狀態確認 ││ AXPress/設值 ││ 視窗/全螢幕PNG ││ CGEventPost  │
└───────┬──────┘└───────┬──────┘└────────┬───────┘└──────┬───────┘
        │               │                │               │
        └───────────────┼────────────────┴───────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ safety.py — 執行期安全閘門與審計                                       │
│   - check_app_allowed(): 阻擋敏感應用程式啟動與聚焦                    │
│   - check_frontmost_allowed(): 前景為密碼庫時阻擋變更動作與截圖        │
│   - audit(): 寫入 ~/.desktop-harness/audit.jsonl 稽核記錄              │
└────────────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ presence.py — 視覺提示層（系統游標疊加層）                            │
│   - 單一實體游標 + 藍色光環（移動）/ 紅色快閃（點擊）                  │
│   - 底部「Agent active — hands off」霓虹提示橫幅                      │
│   - keep_alive(): 主執行緒分片 pump AppKit 事件（杜絕跨執行緒 SIGABRT） │
└────────────────────────────────────────────────────────────────────────┘
```

### 模組職責一覽表

| 模組檔案 | 核心職責 | 關鍵函式 / 類別 |
|----------|----------|-----------------|
| `src/desktop_harness/run.py` | CLI 入口點、參數解析、daemon 存活偵測（0.4s ping）與分流路由、子命令派遣。 | `main()`, `_exec_local()`, `_want_daemon()` |
| `src/desktop_harness/helpers.py` | Agent 呼叫的標準命名空間集散地；整合探索、感知、操作、媒體控制、驗證各項高階 API，並注入 `agent-workspace/agent_helpers.py`。 | `namespace()`, `open_app()`, `click_text()`, `set_field()`, `media_transport()`, `ensure_media_playing()`, `verify()` |
| `src/desktop_harness/windows.py` | 管理 macOS 視窗與應用程式生命週期；NSWorkspace 啟用、`open -a` 備援、焦點輪詢確認、名稱權重排序搜尋。 | `list_apps()`, `list_windows()`, `frontmost_app()`, `find_app()`, `activate()` |
| `src/desktop_harness/ax.py` | 低階 AXUIElement 樹走訪、互動節點篩選、螢幕可視區域過濾（`frame_on_screen`）、文字匹配計分、`AXPress` 執行與屬性設值。 | `ax_snapshot()`, `find()`, `labels()`, `press_element()`, `set_element_value()` |
| `src/desktop_harness/capture.py` | 透過 Quartz 捕捉指定視窗或主螢幕影像；封裝成 NSBitmapImageRep 並轉存為唯一檔名 PNG；執行前強制檢查敏感應用。 | `screenshot()`, `window_info()`, `_save_cgimage()` |
| `src/desktop_harness/input.py` | 實體 HID 輸入注入：`CGWarpMouseCursorPosition` 瞬移游標、`CGEventCreateMouseEvent` / `CGEventPost` 派送點擊、拖曳、捲動與鍵盤事件。 | `mouse_pos()`, `move_to()`, `click()`, `drag()`, `scroll()`, `type_text()`, `hotkey()` |
| `src/desktop_harness/safety.py` | 安全守衛：敏感應用程式名稱與 Bundle ID 黑名單判定；變更動作與截圖前置檢查；稽核日誌寫入。 | `check_app_allowed()`, `check_frontmost_allowed()`, `audit()`, `allow_sensitive()` |
| `src/desktop_harness/daemon.py` | 溫熱常駐伺服端：維護 0600 Unix Domain Socket 與 token；PID 單一實例管理；NDJSON 協定處理 ping、quit、exec。 | `serve()`, `client_request()`, `exec_via_daemon()`, `is_running()`, `stop()` |
| `src/desktop_harness/presence.py` | AppKit 視覺提示層：繪製游標藍光環、紅點閃爍與全螢幕橫幅；實作分片 pump 機制以符合 AppKit 單一主執行緒約束。 | `show()`, `move()`, `click_flash()`, `hide()`, `keep_alive()` |
| `src/desktop_harness/admin.py` | `--doctor` 診斷模組：驗證 PyObjC 模組載入、Accessibility 權限、Screen Recording 權限（實體截圖驗檔大小）、前景 AX 與視窗清單。 | `run_doctor()` |
| `src/desktop_harness/selftest.py` | 非破壞性自測套件：串接 doctor、基礎 helper、滑鼠座標復原、截圖產生、媒體 API、`find_app` 排序、TextEdit 煙霧測試及 daemon 往返。 | `run_selftest()` |
| `src/desktop_harness/demo.py` | 可見煙霧展示：啟動 TextEdit、建立新文件、移動游標至視窗中心、擺動滑鼠、輸入示範字串並展示 Presence 橫幅。 | `run_demo()` |
| `src/desktop_harness/voice_tools.py` | 語音控制擴充（實驗性）：定義 Grok Voice Think Fast 2.0 工具 Schema，並提供對應 harness helper 之本機派送執行器。 | `TOOL_DEFINITIONS`, `execute()`, `SESSION_INSTRUCTIONS` |

---

## 3. 核心資料流

### 3.1 一次典型的 Agent 呼叫時序（含 Daemon 路由與安全檢查）

```
[Agent]               [run.py]            [daemon.py]         [safety.py]        [windows.py]         [ax.py / input.py]
   │                      │                    │                   │                  │                    │
   │─── heredoc 腳本 ────►│                    │                   │                  │                    │
   │                      ├── is_running()? ──►│                   │                  │                    │
   │                      │◄── pong / 0.4s ────│                   │                  │                    │
   │                      │                                        │                  │                    │
   │                      ├── socket exec(code, token) ───────────►│                  │                    │
   │                      │   (或退回 _exec_local)                 │                  │                    │
   │                      │                    │─── 驗證 token ───┤                  │                    │
   │                      │                    │─── 載入 ns ─────►│                  │                    │
   │                      │                    │─── exec() ───────┤                  │                    │
   │                      │                    │                  ├── open_app() ───►│                    │
   │                      │                    │                  │                  ├── check_app() ────►│
   │                      │                    │                  │                  │◄── 通過 ───────────│
   │                      │                    │                  │                  ├── NSWorkspace 啟用 │
   │                      │                    │                  │                  └── 焦點確認 (1.2s) ─►│
   │                      │                    │                  │                                       │
   │                      │                    │                  ├── click_text("儲存") ────────────────►│
   │                      │                    │                  │   ├── check_frontmost_allowed() ─────►│
   │                      │                    │                  │   ├── ax.find(label="儲存") ──────────┤
   │                      │                    │                  │   │    └─ 成功找到 AX 節點             │
   │                      │                    │                  │   ├── AXPress 元素動作 ──────────────┤
   │                      │                    │                  │   └── (若無 AX 動作則退回 input.click) │
   │                      │                    │                  ├── audit log 寫入 ─────────────────┤
   │                      │                    │◄── 腳本完成 ─────┘                                       │
   │                      │◄── {ok, stdout} ───┤                                                          │
   │◄── stdout / stderr ──┤                    │                                                          │
```

### 3.2 感知層階梯架構（Perception Cascade）

```
任務啟動
   │
   ├─► 1. Shell / CLI / 檔案系統處理 ──[能解決]──► 結束（成本 ~0ms）
   │
   ├─► 2. AX 輔助功能樹（ax_snapshot / labels / find）
   │      ├─ 取得結構化屬性（Role, Title, Value, Frame）
   │      └─ 執行 AXPress 或 AXSetAttributeValue ──[能解決]──► 結束（成本 ~10-50ms）
   │
   ├─► 3. 視窗層級截圖（capture.screenshot(app=...)）
   │      └─ 針對 AX 為空（Electron, 遊戲, Canvas）取單一視窗 PNG ──► 視覺推論（成本 50-150ms）
   │
   └─► 4. 全螢幕截圖與 OCR / 視覺模型（最後回落，成本極高）
```

### 3.3 媒體控制保護狀態機（Look-Once, Act-Once）

針對播放器 UI 操作（避免空格鍵 toggle 誤動作），嚴格遵循下列決策迴圈：

```
[呼叫 ensure_media_playing(app)]
             │
             ▼
    執行 media_transport(app) 讀取當前 AX 狀態
             │
             ├─────────────────────────────────────────┐
             ▼                                         ▼
   【偵測到 Pause 鈕已存在】                 【偵測到 Play 鈕（Paused 狀態）】
   狀態：正在播放中                           狀態：暫停中
             │                                         │
             ▼                                         ▼
   直接回傳，不做任何點擊                     僅點擊精確的 Play 鈕一次
   （完全避免重複發送 Space 導致暫停）       （使用 exact=True 避免誤觸 Play all）
             │                                         │
             ▼                                         ▼
            完成                              再次調用 media_transport 驗收
                                                       │
                                                       ▼
                                                      完成
```

### 3.4 視覺提示生命週期與 Main-Thread 約束

- 根據 **ADR-0006**，AppKit 的 `NSWindow` 與 `NSView` 操作嚴格受限於 macOS 主執行緒。任何在背景執行緒存取視窗的方法皆會引發無法捕捉的 **SIGABRT** 崩潰。
- `presence.py` 透過 `keep_alive()` 在主執行緒上分片輪詢事件迴圈（每次 pump 約 0.04s），確保在動作空檔或等待期間，游標藍色光環與底部橫幅依然正常渲染且不當機。

---

## 4. 外部系統相依與邊界

### 4.1 Python 套件依賴（`pyproject.toml`）

| 套件名稱 | 系統介接目標 | 用途說明 |
|----------|--------------|----------|
| `pyobjc-framework-Quartz` | CoreGraphics / WindowServer | 視窗清單擷取（`CGWindowListCopyWindowInfo`）、截圖生成、實體滑鼠移動（`CGWarpMouseCursorPosition`）、鍵鼠事件派送（`CGEventPost`）。 |
| `pyobjc-framework-Cocoa` | AppKit / Foundation | `NSWorkspace` 與 `NSRunningApplication` 管理焦點、`NSBitmapImageRep` 進行 PNG 編碼、Presence 疊加層 UI 繪製。 |
| `pyobjc-framework-ApplicationServices` | HIServices / Accessibility | `AXUIElementCopyAttributeValue` 走訪 UI 樹、`AXUIElementPerformAction` 執行按鈕點擊、`AXIsProcessTrusted` 驗證系統權限。 |

建置系統為 hatchling；wheel 透過 `force-include` 將根目錄 `SKILL.md` 打包成 `desktop_harness/data/SKILL.md`，供 `desktop-harness skill` 子命令輸出。

### 4.2 macOS TCC 權限依賴

| 權限項目 | 系統授權路徑 | 缺乏時的症狀與影響 |
|----------|--------------|-------------------|
| **輔助使用（Accessibility）** | 系統設定 → 隱私權與安全性 → 輔助使用 | `AXIsProcessTrusted()` 回傳 False，無法讀取任何 AX 樹，`CGEventPost` 無法將鍵鼠事件注入其他應用程式。 |
| **螢幕錄製（Screen Recording）** | 系統設定 → 隱私權與安全性 → 螢幕錄製 | `capture.screenshot()` 回傳全黑或空影像，檔案大小小於 1000 bytes。注意：授權後必須完全重啟 Host Terminal / IDE 才會生效。 |

### 4.3 檔案系統執行期足跡

| 檔案 / 目錄路徑 | 權限模式 | 職責與內容說明 |
|-----------------|----------|----------------|
| `~/.desktop-harness/audit.jsonl` | 使用者預設 | 記錄關鍵變更（`activate`, `click_text`, `screenshot`, `ensure_media_playing`）之時間戳記與參數（不記錄輸入內容字串）。 |
| `~/.desktop-harness/daemon.token` | `0600` | 溫熱常駐行程的隨機 hex 認證金鑰。 |
| `~/Library/Caches/desktop-harness/daemon.sock` | `0600` | 本機 Unix Domain Socket，供 CLI 與 Daemon 傳送 NDJSON 訊息。 |
| `~/Library/Caches/desktop-harness/daemon.pid` | `0600` | Daemon 單一實例行程識別碼與存活鎖定。 |
| `$TMPDIR/desktop-harness/capture-<pid>-<ns>.png` | 使用者暫存 | 截圖落地路徑；檔名帶入 PID 與奈秒時間戳記，避免併發時檔案覆蓋。 |
| `~/.grok/skills/desktop-harness/SKILL.md` | 使用者預設 | 透過 `install.sh` 或 `desktop-harness skill` 註冊給 Grok Build 的 Agent 技能設定檔。 |
| `agent-workspace/agent_helpers.py` | 專案目錄 | Agent 自行擴充的自訂函式庫，腳本執行時自動合併進命名空間。 |

### 4.4 網路相依邊界

- **核心桌面控制：100% 本機零網路連線**。所有輔助功能讀取、視窗切換、滑鼠點擊與截圖皆在 Mac 本機端核心與 WindowServer 間進行。
- **實驗性語音控制（選用）**：`scripts/voice_session.py` 連線至 `wss://api.x.ai/v1/realtime`，需要明確提供 `XAI_API_KEY`；若無金鑰則只支援本機 `--dry-run` 模擬測試。
- **更新檢查（選用）**：`desktop-harness check-update` 僅比對 GitHub 上的版本號，不進行背景自動更新。

---

## 5. 安全架構與威脅模型

1. **任意程式碼執行（Arbitrary Exec）表面**：
   - CLI 接收 heredoc 傳入之 Python 原始碼並直接在直譯器中執行。這是產品核心功能（賦予 Agent 靈活組合原語的能力），但代表腳本擁有發起行程者的全部權限（含 `subprocess`、檔案讀寫）。
   - 安全防線分為兩層：**Runtime Gate**（防禦性攔截意外操作）與 **Agent Policy**（Skill 規範禁止越權行為）。
2. **Daemon 本機特權端點**：
   - Daemon 持有已授權的 Accessibility 與 Screen Recording 存取能力。
   - 防禦措施：Socket 檔與 Token 檔嚴格設定為 `0600`（僅同 UID 可讀寫），所有連線必須在請求中傳送正確 Token，否則拒絕。
3. **敏感應用程式雙閘門**：
   - **名稱閘門**：阻擋開啟、切換或針對 1Password、Bitwarden、Keychain、LastPass、Keepass、Dashlane、Nordpass、Enpass、Secrets、Wallet、Bank 等應用的操作。
   - **前景閘門**：當上述敏感應用處於前景時，強制禁止任何變更動作（點擊、打字、快捷鍵、設值）與截圖（截取密碼畫面視為與點擊同等級洩漏）。
   - 覆寫方式：僅在設定 `DH_ALLOW_SENSITIVE=1` 時放行。

---

## 6. 已知限制（誠實條目）

- 前景 HID 為主：控制目標 app 時可能搶焦點；真正背景不搶焦控制尚未實作。
- Electron／部分 web app 的 AX 樹稀疏 → 需視窗截圖回落。
- presence overlay 在多螢幕的座標轉換未保證正確。
- daemon 等於「本機特權 exec 端點」：能連上 socket 並持有 token 的同 UID 行程可執行任意 Python；不應在多人共用機器上常開。
- 任意 `exec` 是產品特性：`DH_*` 閘門只包裹少數 helper，腳本本身可 `import subprocess` 繞過 —— 這是有意的彈性，風險由使用者承擔（見 `SECURITY.md`）。
