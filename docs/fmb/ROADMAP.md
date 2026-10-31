# desktop-harness 路線圖（docs/fmb 版）

> 依「價值 / 工作量 / 風險」排序的下一步 10 項建議。基於 v0.4.2 程式碼現況與 `docs/PRE-RELEASE-REVIEW.md` 的已知議題整理。工作量以「一位熟悉此 codebase 的工程師」估算：S ≈ 半天內、M ≈ 1–3 天、L ≈ 1 週以上。

## 已完成（背景參考）

- [x] AX-first 控制 + CLI + skill
- [x] 真實系統滑鼠（CGWarp + CGEventPost）
- [x] 溫熱 daemon（socket 0600 + token + PID 單實例）
- [x] 安全閘門（敏感 app 開啟/聚焦/前台變更/截圖阻擋）+ audit log
- [x] `selftest`、`install.sh`、`media_transport` / `ensure_media_playing`、`verify()`、presence UI

---

## 下一步 10 項（依價值排序）

### 1. 場景化整合測試腳本（TextEdit / Finder / System Settings 各一條）

- **價值**：目前 `selftest` 只涵蓋 TextEdit 一條淺路徑；多一組可重跑的真實 GUI 劇本，能把 release 前的迴歸抓得更早，也讓 agent 有「驗收範例」可循。
- **工作量**：M
- **風險**：低。非破壞劇本（只讀/復原型操作）需小心設計，避免誤觸系統設定。
- **建議做法**：在 `selftest.py` 或新模組加入 `--scenario` 參數；Finder/Settings 只做 `activate` + `labels` + `find` 等讀取型驗證。

### 2. `menu_click("File", "Save")` 選單列導覽 helper

- **價值**：標準選單是最常見的 GUI 操作之一；沒有它，agent 在「存檔」「偏好設定」這類任務上只能靠 hotkey 或座標亂試。`docs/PRE-RELEASE-REVIEW.md` #12 也列為首要能力缺口。
- **工作量**：M（AX 選單列走訪 + 展開等待 + 子項比對）
- **風險**：中。選單展開時序不穩（需輪詢）、不同 app 選單結構差異。
- **建議做法**：先支援「單層／雙層」路徑；`find` 風格的精確優先匹配；失敗時回報可見子項清單而不是瞎點。

### 3. `wait_for(text/role, timeout=)` 條件等待 helper

- **價值**：目前固定 `wait()` / `wait_stable()` 在慢機器上會 race、快機器上浪費時間；條件等待可同時提升成功率與速度，是多步任務延遲的最大槓桿之一。
- **工作量**：S–M
- **風險**：低。輪詢 `find` 即可；注意輪詢間隔別打爆 AX。
- **建議做法**：`wait_for(text, role=None, timeout=8.0, poll=0.25)`；與 daemon 快取（第 8 項）相乘效果更好。

### 4. 剪貼簿 get/set helper

- **價值**：貼上長文字（`type_text` 每字 8ms）與讀取選取內容都是高頻 agent 需求；也是替代慢速打字的正解。能力缺口 #12 明列。
- **工作量**：S（NSPasteboard 或 `pbcopy`/`pbpaste`）
- **風險**：中。剪貼簿是全域共享狀態 —— 需保存/復原、並寫 audit log；讀剪貼簿可能觸及敏感內容，要過 `check_frontmost_allowed()` 類閘門。
- **建議做法**：`set_clipboard(text)` + `get_clipboard()` + `paste()`（cmd+v）；audit 只記長度不記內容。

### 5. daemon 快照快取（AX walk 結果 100–200ms TTL）

- **價值**：`ensure_media_playing` 一次「按 Play」要 3–4 次完整 AX 走訪；`find` miss 後又有二次取樣走訪。快取能直接砍掉多步任務的主要延遲來源（review #9）。
- **工作量**：M
- **風險**：中。快取過期策略錯了會讓 agent 看到過時 UI；key 需含 `(pid, interactive_only, max_nodes)`。
- **建議做法**：只在 daemon 常駐行程內做；提供 `invalidate()` helper；TTL 保守取 150ms。

### 6. AX 高風險動作閘門補強 + `check_helper_allowed` 清理

- **價值**：安全宣稱要與實作一致（review #1 精神）。v0.4.2 已把前台敏感 app 的變更與截圖擋住了，但 `check_helper_allowed()` 目前仍是「未接線的死 API」，且 `_HIGH_RISK_HELPERS` 名稱並非真實 helper —— 容易讓人誤解安全模型。
- **工作量**：S–M
- **風險**：低（移除或接線都是明確動作）；文件需同步改。
- **建議做法**：二擇一 —— (a) 移除死 API 並在 SECURITY.md 明寫「runtime 阻擋僅覆蓋敏感 app 名稱/前台/截圖」；(b) 在未來 shell helper 落地時才接線。同時把敏感清單改以 bundle id 為主（`"wallet"`/`"bank"` 名稱子字串太寬，review #19）。

### 7. `audit.jsonl` 輪替與保留策略

- **價值**：長跑 agent 會讓 audit log 無限成長；且路徑/保留期目前無文件。小工、直接提升可信度。
- **工作量**：S
- **風險**：低。
- **建議做法**：超過大小門檻（如 5MB）改名 `audit.jsonl.1` 並保留 N 份；文件寫明保留期與「不記錄打字內容」的現況。

### 8. 每次呼叫的 daemon ping 延遲優化

- **價值**：socket 存在但 daemon 掛掉時，每個 CLI 呼叫都白等 0.4s（review #10）；連接失敗也不清 stale socket。
- **工作量**：S
- **風險**：低。
- **建議做法**：ping timeout 降至 50–100ms；connect 失敗時刪 stale sock；connect 前先查 PID 檔存活。

### 9. 真正的背景控制（不搶焦點）

- **價值**：HOW_IT_WORKS 與 README 都把它列為最大待辦；實現後 agent 可多工操作而不打斷使用者。但這是研究級工作。
- **工作量**：L（需評估 AX-only 背景路徑 vs HID 限制）
- **風險**：高。macOS HID 本質是前景的；可能只能對「AX 動作可達」的操作做背景化，需明確降級文件。
- **建議做法**：第一階段先做「AX-only 背景 helper」（`press_element` 不需焦點的情境），文件誠實標示覆蓋率，不宣稱全面背景控制。

### 10. 一鍵 `.app` 權限導引（onboarding）

- **價值**：新使用者最大摩擦是 Accessibility/Screen Recording 授權（還要重啟 host）；一個小 .app 或導引精靈能大幅降低入門門檻。README roadmap 已列。
- **工作量**：L（Swift 小 app 或腳本導引 + AppleScript 提示）
- **風險**：中。打包/簽署與 Gatekeeper 互動；不可假裝能自動授權（macOS 不允許）。
- **建議做法**：先做「偵測缺什麼 → 開啟對應設定 pane → 指引重啟」的精靈（`--doctor` 的延伸），自動授權不在範圍內。

---

## 明確不建議做（非目標）

- 成為通用 computer-use 複製品／預設沙箱 VM 隔離
- CAPTCHA / Cloudflare bypass 類功能（RELEASE.md 明言不收）
- 核心安裝路徑綁定語音實驗（voice 相關維持 optional experimental）
- 靜默自動更新（by design：會動滑鼠的程式碼要由使用者自己決定何時更新）

## 排序後的建議節奏

```
短期（下個 minor）：3 wait_for → 4 剪貼簿 → 8 ping 優化 → 7 audit 輪替
中期：2 menu_click → 1 場景測試 → 6 安全閘門清理 → 5 daemon 快取
長期：9 背景控制 → 10 權限導引 app
```

快速見效（S 級）先做，能立刻降低延遲與摩擦；兩個 L 級項目在前面項目驗收穩定後再啟動。
