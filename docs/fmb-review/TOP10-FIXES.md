# 前十大修補建議與工作量估計

工作量以單一熟悉本 codebase 的工程師估計（含基本手動驗證，不含 CI 建置）。
優先序 = 風險 × 修復成本反向。編號對應 [FINDINGS.md](./FINDINGS.md) 的項目代號。

| # | 項目（對應發現） | 嚴重度 | 工作量 | 建議順位 |
|---|------------------|--------|--------|----------|
| 1 | daemon exec 逾時 + 併發（D1） | 🔴 | 0.5–1 人日 | 立即 |
| 2 | SKILL.md 單一來源與打包衝突（P1） | 🔴 | 0.5 人日 | 立即 |
| 3 | 截圖敏感 gate 補洞（C1、C2） | 🟠 | 0.5 人日 | 高 |
| 4 | 建立 hermetic pytest 測試套件（T3） | 🔴（長期債） | 1–2 人日（首批） | 高 |
| 5 | daemon 單實例 bind 鎖 + is_running 快速失敗（D2、D3） | 🟠 | 0.5 人日 | 高 |
| 6 | voice dry-run 語意 + tool 輪數保險絲（V1、V2） | 🟠 | 0.25 人日 | 中 |
| 7 | 對外 URL / RELEASE 版本 / LICENSE 一致性（P2、P3） | 🟠 | 0.25 人日 | 中 |
| 8 | safety gate 政策化：audit gate_error、處理 `check_helper_allowed`（S1、S2） | 🟠 | 0.25 人日 | 中 |
| 9 | selftest daemon try/finally + 測試分層（T1） | 🟠 | 0.5 人日 | 中 |
| 10 | 整潔批次：constant-time compare、recv cap、魔術數字、`find_app(bool)`、doctor 暫存檔（D4、D5、W1、W2、C3、A1） | 🟡 | 0.5 人日 | 低 |

**合計：約 5–7 人日**（不含補審 5 個未提供檔案可能追加入的工作）。

---

## 各項細節

### 1. daemon exec 逾時 + 併發（D1）— 0.5–1 人日
最少做「per-connection thread + `DH_EXEC_TIMEOUT` 軟逾時（預設 30s）+ 逾時回應客戶端」；文件明講逾時的 thread 無法強殺。若 BOB 要求硬隔離（可強殺、狀態零污染），升級為 exec 走子程序（+0.5–1 人日）。**決策點：** 軟逾時（thread 洩漏可接受）還是子程序隔離。

### 2. SKILL.md 單一來源（P1）— 0.5 人日
根目錄 `SKILL.md` 為唯一真源；`data/SKILL.md` 由 build/安裝步驟產生（或 `skill` 命令直接內嵌讀取）。修完後實際 build 一次 wheel、解開驗證 `desktop_harness/data/SKILL.md` 內容 == 根目錄版（含「Verify, don't assume」段）。**決策點：** 真源放根目錄還是 `data/`。

### 3. 截圖敏感 gate 補洞（C1、C2）— 0.5 人日
- `window_id` 反查 owner → `check_app_allowed`（明確 bug，直接修）。
- 全螢幕模式：掃 on-screen 視窗 owner 命中敏感清單即拒絕，**或**精確改寫 SECURITY.md 措辭。**決策點：** 擋或僅揭露。

### 4. hermetic pytest 首批（T3）— 1–2 人日
不需 GUI/權限即可跑的測項：`safety._looks_sensitive`（含誤擋案例）、`windows.find_app` 排序（monkeypatch `list_apps`）、daemon 協定（`tmp_path` socket + monkeypatch `SOCKET_PATH/TOKEN_PATH`，測 token 拒絕、quit、exec 回應）、`voice_tools.execute` dry-run 分支與未知工具、`capture` 檔名唯一性（不觸發真截圖，測路徑產生函式）。加 `[project.optional-dependencies] dev = ["pytest"]`。**決策點：** 是否加 CI（涉 `.github/workflows`，本任務不得動）。

### 5. daemon 單實例 + is_running（D2、D3）— 0.5 人日
bind-as-lock（EADDRINUSE 即鎖）、probe 逾時降到 0.1s、pid 死亡短路。與 #1 同檔，建議一起動工。

### 6. voice 修正（V1、V2）— 0.25 人日
demo 一律 `dry_run=True`；`MAX_TURNS` 保險絲。皆為小改動、低風險。

### 7. 文件一致性（P2、P3）— 0.25 人日
URL、RELEASE 版本、LICENSE 名義統一。**決策點：** 正式對外 repo 與 LICENSE 名義由 BOB 定。

### 8. safety gate 政策化（S1、S2）— 0.25 人日
gate 例外時 audit `gate_error`（維持 fail-open 但留痕）；`check_helper_allowed` 移除或接線。**決策點：** 是否提供 `DH_STRICT_GATE=1` fail-closed 選項。

### 9. selftest 加固（T1）— 0.5 人日
daemon 測項 try/finally；selftest 分三層輸出（hermetic / GUI / daemon）讓 CI 可只跑第一層。

### 10. 整潔批次 — 0.5 人日
`secrets.compare_digest`、recv 16MB cap、`NSBitmapImageFileTypePNG`、`NSApplicationActivateIgnoringOtherApps`、`find_app(bool)` 排除、doctor 改用 capture 預設路徑。全是小改，一次 PR 收掉。

---

## 建議驗收方式（修完後手動檢查）

- daemon：送 `{"op":"exec","code":"import time; time.sleep(999)"}` → 逾時回應、daemon 仍可 ping；同時開第二個 client 確認不被卡。
- 打包：`pip wheel .` 後解開，確認 `data/SKILL.md` 與根目錄一致。
- 截圖：1Password 開在背景（非前景）時 `screenshot(window_id=...)` 被拒。
- `pytest`（首批 hermetic）在無 GUI 環境全綠。
- selftest 中途 kill 掉 daemon 確認不殘留。
