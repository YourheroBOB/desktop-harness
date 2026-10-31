# desktop-harness 路線圖（docs/fmb 版）

> 依「價值 / 工作量 / 風險」綜合排序的下一步 10 項工程改進項目。基於 v0.4.2 程式碼現況、`docs/PRE-RELEASE-REVIEW.md` 審查結論與 `docs/fmb-perf/` 效能報告整理。
> 工作量估算（以熟悉此 Codebase 的資深工程師為準）：
> - **S**：半天以內（≤ 4 小時）
> - **M**：1 至 3 個工作天
> - **L**：1 週以上（具架構重構或系統底層調研風險）

---

## 現狀回顧（已完成項目）

- [x] AX-First 結構化感知階梯 + CLI 進入點 + Grok Build Skill 自動註冊。
- [x] 實體系統游標操控（`CGWarpMouseCursorPosition` + `CGEventPost`）。
- [x] 溫熱 Daemon 機制（Unix Socket 0600 + Token 驗證 + 單一實例 PID 檔）。
- [x] 安全閘門（敏感 App 名稱/Bundle ID 啟動防禦、前景變更防禦、前景敏感截圖防禦、Audit 日誌）。
- [x] 健檢與測試鏈（`--doctor`、非破壞性 `selftest`、可視化 `demo`、Look-Once 媒體控制狀態機、`verify()` 驗證閉環）。
- [x] 單一系統游標 Presence UI（藍色移動光環、紅色點擊光環、底部防手滑霓虹橫幅、主執行緒防崩潰分片 pump）。

---

## 下一步 10 項核心任務（依價值降序排列）

### 1. `wait_for(text/role, timeout=)` 條件等待 Helper

- **價值**：目前程式碼多處仰賴固定 `wait()` / `wait_stable()`（固定 0.2–0.4 秒）。在高性能 Mac 上浪費時間，在負載重時則引發競爭條件（Race）導致元素未渲染就被點擊。條件式輪詢可同時提升成功率與多步驟吞吐量。
- **工作量**：S–M
- **風險**：低。以短週期（0.15–0.25 秒）輪詢 `find()` 即可；需設定超時保護（預設 8.0 秒），避免打爆 AX 呼叫。
- **具體方案**：在 `helpers.py` 實作 `wait_for(query, role=None, timeout=8.0, poll_interval=0.2)`；時限內找到節點即回傳節點屬性，超時拋出清楚的 `TimeoutError`。

### 2. `menu_click("File", "Save")` 選單列走訪 Helper

- **價值**：系統標準選單列是 Mac 自動化最高頻操作之一（存檔、偏好設定、匯出）。目前缺乏直達原語，Agent 常退回盲猜熱鍵或全螢幕座標點擊，極易失敗。
- **工作量**：M
- **風險**：中。選單展開具動畫時延，且不同 app 的選單列 AX 階層略有差異；需處理多層（Menu → MenuItem → Submenu）展開等待。
- **具體方案**：透過前景 app 的 `AXMenuBar` 節點走訪，比對一級選單標題後 `AXPress` 展開，輪詢可見子選單再比對二級目標點擊；失敗時輸出當前層級可見清單以利 Agent 修正。

### 3. 剪貼簿操作 Helper（`get_clipboard` / `set_clipboard` / `paste`）

- **價值**：目前文字輸入全靠 `type_text`（逐字發送 CGEvent，每字延遲 8ms）。輸入長文或程式碼片段極慢，且不支援複雜格式。剪貼簿貼上是長字串注入的標準解法。
- **工作量**：S
- **風險**：中。剪貼簿是全域共享資源，操作可能覆蓋使用者暫存，且讀取可能涉及機密字串。
- **具體方案**：以 `AppKit.NSPasteboard` 實作 `set_clipboard()` / `get_clipboard()` 與封裝熱鍵的 `paste()`；`safety.py` 僅記錄長度不記內文，並在前景為敏感 app 時阻擋讀寫。

### 4. Daemon 併發與連線穩健性重構（P0 防禦）

- **價值**：`docs/fmb-perf/findings-daemon.md` 指出，目前 Daemon 採單執行緒 Accept 迴圈且未設 Socket 連線逾時；遇客戶端掛起或突發斷線，會造成 Daemon 無回應或因未捕捉例外而崩潰。
- **工作量**：M
- **風險**：低至中。涉及網路迴圈底層，需確保 NDJSON 協定向後相容。
- **具體方案**：(1) 連線設定明確逾時（`conn.settimeout(5.0)`）；(2) 加完整 `try/except`，單一客戶端異常不得中斷主監聽迴圈；(3) 為伺服端 `exec` 導入超時控制。

### 5. Daemon 內 AX 快照快取（100–200ms TTL）

- **價值**：多步驟複合操作（如 `ensure_media_playing`、連續表單填寫）中，一次決策常觸發 3–4 次完整 AX 走訪，耗費數百毫秒。短 TTL 快取可顯著降低感知延遲。
- **工作量**：M
- **風險**：中。快取失效策略若過寬，Agent 會看到過期 UI 並誤判；Key 必須嚴格綁定 `(pid, interactive_only, max_nodes)`。
- **具體方案**：僅在常駐 Daemon 行程內建微型快取字典，TTL 預設 150ms；提供 `invalidate_cache()` 供突變操作後主動清除。

### 6. 場景化整合測試套件（TextEdit / Finder / System Settings）

- **價值**：現行 `selftest` 僅覆蓋 TextEdit 一條淺路徑。擴充 Finder 視窗瀏覽與 System Settings 只讀走訪等標準劇本，可於發版前捕捉更多 macOS 版本間的 AX 語意迴歸。
- **工作量**：M
- **風險**：低。劇本須維持非破壞性（只讀 `labels`、驗證視窗清單，不做系統修改）。
- **具體方案**：在 `selftest.py` 增加可選參數 `--scenario=textedit,finder,settings`，並設計清楚的驗收斷言矩陣。

### 7. 暫存截圖自動清理與 `audit.jsonl` 輪替政策

- **價值**：效能審查（PERC-3、TR-4）指出，截圖寫入暫存目錄卻永不清除，長期運作的 Agent 或 Observe Loop 會堆積大量 PNG；`audit.jsonl` 亦無容量上限。
- **工作量**：S
- **風險**：低。
- **具體方案**：(1) `capture.py` 加入輕量 sweep，清理超過 24 小時的過期 `capture-*.png`；(2) `safety.audit()` 加大小檢查，超過 5MB 時旋轉為 `audit.jsonl.1`，保留最近數份。

### 8. Daemon 存活偵測（Ping）調優與 Stale Socket 清理

- **價值**：若前次 Daemon 異常終止但 Socket 檔殘留，CLI 每次執行都要白等 0.4 秒連線超時，拖慢降級速度。
- **工作量**：S
- **風險**：低。
- **具體方案**：Ping 逾時縮短至 0.08–0.1 秒；連線前先檢查 PID 檔行程存活性；連線失敗且行程已死時主動刪除 stale socket 與 pid 檔。

### 9. 安全閘門規則強化（Bundle ID 精確比對與死程式碼清理）

- **價值**：目前敏感應用以名稱子字串比對，`"bank"`、`"wallet"` 等易誤報；且 `safety.check_helper_allowed()` 仍是未接線的死 API，容易讓外界誤解安全模型。
- **工作量**：S–M
- **風險**：低。
- **具體方案**：黑名單改以精確 Bundle ID 為主、保留少數嚴格名稱匹配；清理未啟用 hook，並在文件中精確敘述安全邊界。

### 10. 背景無焦點控制探索（Background Control via AX-Only）

- **價值**：目前任何 HID 輸入皆會把目標視窗帶到前景，打斷使用者。若純 AX 支援的元件可後台操作，Agent 即可多工協同。
- **工作量**：L
- **風險**：高。macOS HID 本質是前景導向；無法透過 AX 觸發的自訂渲染元件完全無法背景點擊。
- **具體方案**：第一階段區分「AX-only 背景動作」與「前景 HID 動作」，實作 `press_background(app, query)`：不呼叫 `windows.activate()`，直接對目標 AX 節點 `AXUIElementPerformAction`，並在文件誠實標註支援極限。

---

## 研發排程節奏建議

```
【第一階段：穩定性與即時效益（S–M 級，1 週內）】
  ├─ 任務 1：wait_for 條件等待 Helper（消除時序競爭）
  ├─ 任務 3：剪貼簿操作 Helper（長字串輸入提速）
  ├─ 任務 8：Daemon Ping 延遲調優與 Stale 清理
  └─ 任務 7：截圖清理與 Audit 日誌輪替

【第二階段：核心能力與架構加固（M 級，2–3 週）】
  ├─ 任務 2：選單列導覽 menu_click
  ├─ 任務 4：Daemon 併發穩健性重構
  ├─ 任務 5：Daemon AX 快照快取
  ├─ 任務 6：場景化整合測試套件
  └─ 任務 9：安全閘門清理與 Bundle ID 精確化

【第三階段：深度探索（L 級，長期規劃）】
  └─ 任務 10：背景無焦點控制探索
```

---

## 明確排除項目（Non-Goals）

1. **封閉式沙盒或虛擬機隔離**：本專案定位為控制真實 Mac 的實體雙手，非 VM 隔離環境。
2. **CAPTCHA / 雲端防護繞過機制**：明確拒絕整合任何驗證碼破解模組。
3. **強制靜默自動更新**：具備鍵鼠控制權限的工具，其程式碼更新必須完全由使用者手動授權與觸發。
4. **預設綁定網路語音核心**：核心 CLI 維持零網路依賴；語音功能維持選用且獨立的實驗腳本形態。
