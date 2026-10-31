# desktop-harness 可觀測性設計（docs/fmb-observability）

> **版本：** v0.1（設計稿，基於 repo v0.4.2 程式現況）
> **狀態：** 設計文件。本目錄只新增文件，不含任何程式碼變更；所有「落地建議」都標記為後續工作項目。
> **範圍：** `desktop-harness` CLI、溫熱 daemon、`--doctor` / `selftest` / `demo`、實驗性 voice 路徑。

---

## 1. 目標

1. 盤點現有的日誌、指標、錯誤回報（見 `CURRENT-STATE.md`）。
2. 定義關鍵事件與欄位 schema（見 `EVENTS.md`）。
3. 定義建議指標與 SLO（見 `METRICS-SLO.md`）。
4. 定義告警條件與處置（見 `ALERTS.md`）。
5. 定義儀表板版面（見 `DASHBOARD.md`）。
6. 定義日誌中禁止出現的敏感欄位清單與 redaction 規則（見 `SENSITIVE-FIELDS.md`）。

## 2. 非目標（明確不做）

- **不引入外部監控 / APM / SaaS。** 本工具是「本機優先、隱私優先」的桌面控制程式，觀測資料一律落地在本機。
- **不連線任何正式服務**（Observability 也適用同一規則）。
- **不改既有 `audit.jsonl` 格式**，只做向下相容的延伸與補強。
- **不收集螢幕內容、輸入內容、剪貼簿、任何憑證。**

## 3. 設計原則

| # | 原則 | 理由 |
|---|------|------|
| 1 | 結構化 JSONL，一行一事件 | 既有 `audit.jsonl` 已是 JSONL，保持一致、可用 `jq` 本地分析 |
| 2 | 最小可用欄位；預設只記中繼資料（計數／長度／雜湊） | 桌面控制工具的最大風險就是把「使用者輸入」寫進日誌 |
| 3 | 敏感欄位分級 + 靜態掃描 | 讓「禁止入欄」變成可驗證的規則，不是口號 |
| 4 | 靜默失敗是可觀測性的敵人 | 現有 `safety.audit()` 的 `except: pass` 會讓觀測失效且無人知曉 |
| 5 | 本機 SLO 是「基線 + 趨勢」，不是 24/7 on-call | 單機工具沒有服務級營維團隊 |
| 6 | 可漸進採用 | 先政策文件 → 再依 `docs/fmb/ROADMAP.md` 排程埋點 |

## 4. 檔案導覽

| 檔案 | 內容 |
|------|------|
| `CURRENT-STATE.md` | 現況盤點：各模組已有的日誌／指標／錯誤回報與缺口 |
| `EVENTS.md` | 事件模型、事件目錄、欄位命名規範、保留與輪替 |
| `METRICS-SLO.md` | 本機指標模型、指標清單、SLO 提案（初期基線，待實測校正） |
| `ALERTS.md` | 告警條件、嚴重度、處置 runbook 連結（本地優先） |
| `DASHBOARD.md` | 儀表板版面規格與每日報告格式（純本機產生） |
| `SENSITIVE-FIELDS.md` | 敏感欄位分級、FORBIDDEN 清單、redaction 規則、好壞日誌範例 |

## 5. 資料落地位置與開關（提案，尚未實作）

| 項目 | 值 | 說明 |
|------|----|------|
| 事件檔 | `~/.desktop-harness/events.jsonl` | 新；env `DH_EVENTS_LOG` 可覆寫 |
| 指標檔 | `~/.desktop-harness/metrics.jsonl` | 新；env `DH_METRICS_LOG` 可覆寫 |
| 審計檔 | `~/.desktop-harness/audit.jsonl` | **既有，不變**；env `DH_AUDIT_LOG` |
| 總開關 | `DH_OBSERVABILITY=0` | 關閉新事件／指標寫入（audit 安全閘門不受影響） |
| 詳細度 | `DH_LOG_WINDOW_TITLES=1` | 預設關；開啟後視窗標題才可入欄（見 `SENSITIVE-FIELDS.md`） |

所有新環境變數必須同步回 `docs/fmb/ARCHITECTURE.md` 第 3.4 節的環境變數表（本次不改動既有檔案，列為後續工作）。

## 6. 落地節奏（對齊 `docs/fmb/ROADMAP.md`）

```
Phase 0（本文件）      政策與 schema 定稿
Phase 1                audit 輪替 + redaction（ROADMAP #7）
Phase 2                events.jsonl 事件骨架 + audit_write_failed 可見化
Phase 3                metrics.jsonl + `desktop-harness report` 本地彙總
Phase 4                告警規則常駐化 + DASHBOARD.md 落地為報告產出器
```

> 以上 Phase 1–4 為**後續實作工作**，不在本次範圍；本次只交付設計與規範。

## 7. 一致性聲明

- 本設計不修改任何執行路徑、不新增依賴、不連網。
- 文件中所有範例值皆為 `FAKE_VALUE_FOR_TEST` 之類的明顯假字串。
- 若本文件與程式碼實況衝突，以程式碼為準並修訂本文件（文件稍晚於事實是可接受的；文件假裝事實不存在則不可接受）。
