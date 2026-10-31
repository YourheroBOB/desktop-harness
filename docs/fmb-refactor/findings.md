# 結構問題盤點（findings）

> 每一項標記證據來源：**〔直接〕** = 本規劃直接檢視原始碼；**〔引用〕** = 引自 `docs/PRE-RELEASE-REVIEW.md`（含程式碼摘錄）、`docs/fmb-perf/`、`docs/fmb-adr/`，動手前需重讀最新原始碼。編號慣例：D=重複、L=過長函式、C=耦合、N=命名。

## 1. 重複程式（D）

| ID | 位置 | 問題 | 證據 | 處置批次 |
|----|------|------|------|----------|
| D1 | `capture.py` `screenshot()` 與 `window_info()` | 兩處各自寫「列舉視窗 → 子字串匹配」迴圈；`screenshot` 匹配 app 名**或** title，`window_info` 只匹配 app 名，差異隱晦且無共用實作 | 〔直接〕 | 批次 1 |
| D2 | `safety.py` `_SENSITIVE_NAME_SUBSTR` / `_SENSITIVE_BUNDLE_SUBSTR` | 兩 tuple 有 8 項完全重疊（bundle 清單是 name 清單的子集），新增項目要記得改兩處 | 〔直接〕 | 批次 2 |
| D3 | `admin.py` `run_doctor()` | 五個檢查項重複同一個 `try/except → check()` 樣板；`AXIsProcessTrusted` 被 import 兩次（pyobjc 檢查與 Accessibility 檢查各一次） | 〔直接〕 | 批次 3 |
| D4 | `scripts/voice_session.py` | `from desktop_harness.voice_tools import …` 在 `main()` 與 `run_session()` 各 import 一次；`main()` import 的 `SESSION_INSTRUCTIONS` 從未使用 | 〔直接〕 | 批次 4 |
| D5 | `scripts/voice_session.py` `run_session()` | `json.dumps({"type": "conversation.item.create", …})` 組裝重複兩次（文字 turn 與 function_call_output）；事件型別在 tuple 與 `elif` 鏈中重複列舉 | 〔直接〕 | 批次 4 |
| D6 | `SKILL.md`（repo 根）與 `src/desktop_harness/data/SKILL.md` | 同一文件兩份，靠 `pyproject.toml` force-include 打包，需人工保持同步（歷史上曾因此出錯，ADR-0002 已記載） | 〔引用〕 | 記錄不排批（見 §5） |
| D7 | `demo.py` / `selftest.py` / `scripts/observe-demo.sh` | 「開 TextEdit → 打字 → 讀 labels」的煙霧邏輯在三處各自實作（observe-demo 走獨立 heredoc 腳本尚可，demo 與 selftest 的重疊可收斂） | 〔直接〕demo.py；〔引用〕selftest 描述 | 記錄不排批（優先級低） |
| D8 | `helpers.click_text` / `ensure_media_playing` | 一次「按 Play」做 3–4 次完整 AX walk；`find` miss 後另取樣 walk 一次 | 〔引用〕review #9 | 批次 5 |

## 2. 過長函式 / 混雜職責（L）

| ID | 位置 | 問題 | 證據 | 處置批次 |
|----|------|------|------|----------|
| L1 | `admin.py` `run_doctor()`（約 75 行） | 單函式混：輸出格式、五項檢查實作、致命錯誤早退、失敗摘要。加新檢查項要在函式體內再塞一個 try/except 區塊 | 〔直接〕 | 批次 3 |
| L2 | `scripts/voice_session.py` `run_session()` | 單一 async 函式混：連線、session 設定、文字 turn、事件分發、工具執行、結果回傳、續 turn 邏輯 | 〔直接〕 | 批次 4 |
| L3 | `capture.py` `screenshot()` | 一函式五種職責：safety gate、輸出路徑生成、視窗匹配、兩種擷取分支、audit 寫入 | 〔直接〕 | 批次 1（拆匹配）；其餘職責拆分列為後續可選 |
| L4 | `helpers.click_text` | pid 路徑的 inline 條件運算式可讀性差且有型別 bug（見 N/C-項與 review #6） | 〔引用〕 | 批次 5 |
| L5 | `ax.walk` 互動節點過濾 | 巢狀分支後幾乎所有節點 `keep=True`，難以推理（review #15） | 〔引用〕 | 批次 5 |

## 3. 耦合過緊（C）

| ID | 位置 | 問題 | 證據 | 處置批次 |
|----|------|------|------|----------|
| C1 | `capture.py` → `windows` | capture 直接消費 `list_windows()` 回傳 dict 的內部鍵形狀並自行匹配，而非委託 windows 提供查找函式；匹配策略與 `windows.find_app` 的「exact > prefix > substring」精神不一致（D1 的根因） | 〔直接〕 | 批次 1 |
| C2 | `safety.check_frontmost_allowed()` 惰性 `from . import windows` | 為迴避 safety↔windows 循環 import 而惰性匯入；gate 的呼叫點散落各模組，**新增變異動作時須記得手動加 gate**（ADR-0008 已將此顯性化為規範） | 〔直接〕 | 批次 2（僅加註解與測試釘住）；結構性解法（集中 gate decorator）列為後續評估 |
| C3 | 模組層副作用：`safety._AUDIT`、`capture.TMP` | 兩者都在 **import 時**讀環境變數／`mkdir`。測試想覆寫 `DH_AUDIT_LOG` 必須在 import 前設好 env（或 reload 模組），是可測性的主要摩擦點 | 〔直接〕 | 批次 1（TMP）、批次 2（_AUDIT） |
| C4 | `run.py` → `daemon.is_running()`（ping timeout 0.4s） | 每次 CLI 呼叫都付 daemon ping 成本，daemon 掛掉時全慢 400ms（fmb-perf DAEMON-4）。屬效能修復（fmb-perf 範圍），但重構 `run.py` 路由邏輯時應一併考慮介面化 | 〔引用〕 | 不排批；在 fmb-perf 修復時順手介面化 |
| C5 | `voice_session` dry-run 與 live 路徑對 `execute()` 的引數型別不一致（見 N4） | 型別契約鬆散使兩條路徑行為可能分岔 | 〔直接〕 | 批次 4 |

## 4. 命名不一致（N）

| ID | 位置 | 問題 | 證據 | 處置批次 |
|----|------|------|------|----------|
| N1 | 各模組 import 別名 | `windows as winmod`、`helpers as H`（demo.py）、`safety as _safety`（capture.py）— 三種風格並存 | 〔直接〕 | 各批次內統一為完整模組名（`from . import windows, safety`），不單獨開批 |
| N2 | `safety.check_helper_allowed()` | 名稱暗示已接線的 gate，實際上**從未被呼叫**；阻擋清單以區域變數內嵌，review 直指為「死 API、易誤解安全模型」（ROADMAP #6 亦列） | 〔直接〕函式存在；〔引用〕未被呼叫 | 批次 2 |
| N3 | `capture._save_cgimage()` 魔術數字 `4` | 應使用 `NSBitmapImageFileTypePNG` 常數；另 `NSImage` import 後未使用 | 〔直接〕 | 批次 1 |
| N4 | `voice_session.py` | `execute(name, arguments, …)` live 路徑傳 **JSON 字串**、dry-run demo 傳 **dict**（變數還叫 `args_`）；`et` 縮寫難讀 | 〔直接〕 | 批次 4 |
| N5 | `admin.py` doctor 固定輸出 `dh-doctor.png` | 與 `capture.screenshot` 已改為「每次唯一檔名」的策略不一致，且併發執行會互相覆蓋（PERC-4） | 〔直接〕 + 〔引用〕 | 批次 3 |
| N6 | `ax._ax_point` 魔術型別整數 `1` / `2` | 應用 `kAXValueCGPointType` / `kAXValueCGSizeType`（review #14） | 〔引用〕 | 批次 5 |

## 5. 記錄但不排批的項目

- **D6（SKILL.md 雙份）**：根治需要動打包與 `skill` 子命令（讀取路徑改 `importlib.resources`），牽涉 pyproject 與發佈流程，不適合與純結構重構混批。建議在 ROADMAP 的「安全閘門清理」（第 6 項）或獨立 packaging PR 處理。
- **D7（煙霧邏輯重複）**：demo 與 selftest 的重疊收斂屬低價值打磨，且 selftest 原始碼未直接檢視，先記錄。
- **audit log 靜默吞例外、無輪替**（TR-4 / OBS-2）：屬 fmb-perf 修復範圍；批次 2 只做結構調整並**刻意保持**現有吞例外行為，避免重構與行為修復混在同一 PR。
