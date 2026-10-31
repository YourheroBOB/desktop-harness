# desktop-harness 重構計畫（docs/fmb-refactor）

- **日期：** 2026-08（結構重構專項規劃）
- **性質：** 本目錄僅為**重構計畫文件**，未修改任何原始碼。所有「重構後」程式碼皆為提案，需另行開分支、逐批實作與驗證。
- **repo：** YourheroBOB/desktop-harness @ v0.4.2

---

## 1. 目的與範圍

針對 v0.4.2 程式碼盤點四類結構問題，並提出**可分批進行、每批可獨立驗證**的重構計畫：

1. **重複程式**（duplication）
2. **過長函式 / 混雜職責**（long function, mixed concerns）
3. **耦合過緊**（tight coupling：模組層副作用、跨模組自行實作對方職責、隱含循環依賴）
4. **命名不一致**（naming / alias / 常數）

### 檢視視野與限制（先講清楚）

本計畫**直接檢視**了以下檔案：`safety.py`、`admin.py`、`capture.py`、`demo.py`、`__init__.py`、`scripts/voice_session.py`、`scripts/observe-demo.sh`、`agent-workspace/agent_helpers.py`、`install.sh`、`pyproject.toml`。

以下檔案**未在直接檢視視野內**，相關發現引自 `docs/PRE-RELEASE-REVIEW.md`（其內含程式碼摘錄）、`docs/fmb-perf/`、`docs/fmb-adr/` 與 `docs/fmb/ARCHITECTURE.md`，均已標記「引用」：

- `src/desktop_harness/helpers.py`、`ax.py`、`input.py`、`run.py`、`daemon.py`、`presence.py`、`selftest.py`、`voice_tools.py`、`windows.py`

**凡標記「引用」的項目，動手重構前必須先重讀最新原始碼確認現況**（對應批次計畫中已列為前置步驟）。

---

## 2. 檔案索引

| 檔案 | 內容 |
|------|------|
| [findings.md](./findings.md) | 四類結構問題的完整盤點（含證據來源標記） |
| [plan-01-capture-window-matching.md](./plan-01-capture-window-matching.md) | 批次 1：capture/windows 視窗匹配去重、模組層副作用移除 |
| [plan-02-safety-testability.md](./plan-02-safety-testability.md) | 批次 2：safety 測試化（lazy env）、敏感清單合併、死 API 誠實化 |
| [plan-03-admin-doctor.md](./plan-03-admin-doctor.md) | 批次 3：`run_doctor` 資料驅動化 + 輸出檔名唯一化 |
| [plan-04-voice-session.md](./plan-04-voice-session.md) | 批次 4：`voice_session.py` 拆分 + `execute()` 引數型別一致化 |
| [plan-05-helpers-ax.md](./plan-05-helpers-ax.md) | 批次 5（高風險，引用推論）：helpers/ax 的 pid 處理、media 狀態機、重複 AX walk |

## 3. 批次總覽與順序原則

依「風險由低到高、可獨立驗收」排序；每一批 = 一個獨立 PR，先補特徵測試（characterization test）再動結構：

| 批次 | 範圍 | 風險 | 行為變更 | 驗證 |
|------|------|------|----------|------|
| 1 | `capture.py` / `windows.py`（新函式） | 低 | 視窗匹配優先級明確化（exact > substring）；`window_info` 行為保持 | 純函式單測 + `--doctor` + 截圖煙霧 |
| 2 | `safety.py` | 低 | `DH_AUDIT_LOG` 改為「呼叫時」讀取（原為 import 時） | 單測（monkeypatch env）+ selftest |
| 3 | `admin.py` | 低 | doctor 輸出檔名唯一化 + 用後清理（PERC-4） | `--doctor` 全 PASS + 單測 |
| 4 | `scripts/voice_session.py` | 中 | dry-run 傳給 `execute()` 的引數型別統一（先以特徵測試釘住現況） | `--dry-run --list-tools` 離線驗證，零網路 |
| 5 | `helpers.py` / `ax.py` | 高 | 修 pid crash、media 死分支、重複 walk（皆為 review 已列 bug） | 特徵測試 + selftest + demo |

**共通原則：**

1. **行為保持優先**：除非該批明列「行為變更」，重構前後對外可觀察行為必須相同。
2. **先測試後重構**：每批的第一步都是補特徵測試（見各批「需先補的測試」），沒有測試的批次不動手。
3. **驗證邊界**：沿用 `docs/fmb-perf/verification-plan.md` 的隔離矩陣 — `DH_SOCKET`／`DH_TOKEN_PATH`／`DH_AUDIT_LOG` 指向 `tmp_path`、`DH_NO_DAEMON=1`、不連任何網路服務、假憑證一律 `FAKE_VALUE_FOR_TEST`、不讀寫 repo 外路徑（`tempfile`／`tmp_path` 沙箱除外）、不動正在跑的使用者 daemon。
4. **一批一 PR**：跨模組的重構（如批次 1 新增 `windows.find_window` 並改 `capture.py`）視為同一批，因為拆開會產生「新增但無人使用」的中間狀態。
5. **不在重構 PR 內順手修 bug**：fmb-perf 已列的 P0/P1 修復（DAEMON-1~3、TR-1~4 等）與結構重構分開進行，避免單一 PR 難以審查。

## 4. 與既有文件的關係

- 效能／可靠性修復（timeout、資源洩漏等）→ `docs/fmb-perf/`，本計畫不重複展開，只在其修復會因結構問題而變難時點出關聯。
- 架構決策背景 → `docs/fmb-adr/`；本計畫的所有重構**不改變任何 ADR 的決策**（AX-first、CLI-not-MCP、daemon token、AppKit main-thread 等）。
- 功能路線（wait_for、menu_click、剪貼簿等）→ `docs/fmb/ROADMAP.md`，不屬於重構範圍。
