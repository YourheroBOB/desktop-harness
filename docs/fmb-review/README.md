# desktop-harness 程式碼審查報告（fugu-max pass, 2026）

- **Repo：** `YourheroBOB/desktop-harness`（v0.4.2）
- **審查者角色：** 資深軟體工程師 / 逐檔 code review
- **本次變更：** 僅新增 `docs/fmb-review/` 下的 Markdown 報告，未修改任何既有檔案
- **文件：**
  - [FINDINGS.md](./FINDINGS.md) — 逐檔具體問題（檔案:行號、嚴重度、說明、建議修法）
  - [TOP10-FIXES.md](./TOP10-FIXES.md) — 前十大修補建議與工作量估計

---

## 審查範圍與方法

依 repo 提供的 35 個檔案內容逐檔審查，涵蓋：正確性、併發、錯誤處理、可讀性、可測試性、相依風險（pyobjc / macOS API / 第三方文件一致性）。對照 `docs/PRE-RELEASE-REVIEW.md`（前次審查）複驗修復狀態。

### ⚠️ 範圍限制（重要）

以下核心檔案的內容**未提供**給本次審查，相關結論僅能由其他檔案間接推論，列為未完成事項：

- `src/desktop_harness/helpers.py`（mutation gates、`click_text` pid 路徑、audit 覆蓋範圍）
- `src/desktop_harness/ax.py`（`_ax_point` 常數、walk 過濾邏輯、`frame_on_screen` 實作）
- `src/desktop_harness/input.py`（`_KEYCODES` 覆蓋、click settle sleeps）
- `src/desktop_harness/presence.py`（main-thread AppKit 規則、`keep_alive`）
- `src/desktop_harness/run.py`（daemon 自動路由、`_want_daemon` ping 成本、`skill` 命令讀取來源）

前次審查中與這些檔案相關的 High 級項目（前景敏感 app 的 click/type/hotkey gate、`click_text(int pid)` crash、hotkey 鍵碼覆蓋、daemon ping 延遲）**無法複驗**，請在補齊內容後重審。

---

## 嚴重度統計（本次可直接驗證的檔案）

| 嚴重度 | 數量 | 代表問題 |
|--------|------|----------|
| 高 | 2 | daemon exec 無逾時可永久卡死；SKILL.md 雙份漂移 + 打包路徑衝突 |
| 中 | 10 | 單實例 TOCTOU、截圖敏感 gate 洞、fail-open gate、無 hermetic 測試、repo URL 不一致等 |
| 低 | 15+ | magic numbers、死碼、暫存檔互蓋、文件漂移等 |

---

## 前次審查（PRE-RELEASE-REVIEW.md）修復狀態複驗

### 已修（可由本次內容驗證）

| 前次 # | 項目 | 現況 |
|--------|------|------|
| 2 | daemon 無認證 | ✅ token（0600）+ socket 0600 + PID 單實例（`daemon.py`）；殘留 TOCTOU 見本次 D2 |
| 3 | 版本不一致 | ✅ `__init__.py` = `pyproject.toml` = 0.4.2 |
| 5 | 私有路徑外洩 | ✅ `install.md` 已改為 GitHub clone 流程 |
| 6 | `find_app(int)` crash | ✅ `windows.find_app` 有 pid 路徑；selftest 有排名斷言 |
| 7 | find_app first-hit | ✅ exact > startswith > shortest-substring 分層 |
| 8 | media_transport 死分支 | ✅ selftest 斷言 `transport_play` / `row_play` / `play == transport_play` |
| 17 | screenshot 固定檔名 | ✅ `capture-{pid}-{ns}.png`（但 doctor 未跟進，見 A1） |
| 21 | doctor `len(nodes) >= 0` | ✅ 改為 `> 0`（衍生新誤判風險，見 A2） |
| 1（部分） | 敏感 app gate | ⚠️ `safety.check_frontmost_allowed` 存在且 `capture.py` 有接；helpers 端 mutation gate 無法驗證 |

### 未修 / 部分修

| 前次 # | 項目 | 現況 |
|--------|------|------|
| 1（部分） | `check_helper_allowed` 死碼 | ❌ 仍無任何呼叫者（本次 S2） |
| 4 | SKILL.md 打包 | ⚠️ 改用 hatch force-include，但產生雙份漂移 + 同路徑衝突新問題（本次 P1） |
| 16 | agent_helpers 需重啟 daemon | ❌ 無 reload op（本次 D6） |
| 18 | audit 無輪替 | ❌（本次 S4） |
| 19 | sensitive 子字串過廣 | ❌ `"secrets"/"wallet"/"bank"` 仍在名稱比對（本次 S3） |
| 22 | voice dry-run 實際執行 | ❌ `voice_session.py` 仍以 `dry_run=False` 跑 demo（本次 V1） |
| — | 無自動化測試 | ❌ repo 無 tests/、pyproject 無 dev deps（本次 T3） |

---

## 決策點摘要（詳見 TOP10-FIXES.md）

1. `check_frontmost_allowed` 例外時 fail-open（現行）還是 fail-closed？
2. 全螢幕截圖遇到「可見但非前景」的敏感視窗：擋下、警告、或僅文件揭露？
3. SKILL.md 唯一來源放根目錄還是 `data/`？
4. repo 對外正式 URL 與 LICENSE 名義（文件寫 `xfreeze2`，實際 repo 為 `YourheroBOB`）。
5. daemon 是否需支援併發請求（影響修法：per-connection thread vs subprocess 隔離）。
6. 是否引入 pytest / CI（涉及 `.github/workflows`，本任務不得改，屬 BOB 決策）。
