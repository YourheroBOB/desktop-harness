# desktop-harness 授權與資料合規盤點（fmb-compliance）

- **日期：** 2026-08（授權與資料合規專項盤點）
- **範圍：** 相依套件授權相容性、程式處理的個人資料類別與流向、保存與刪除機制、記錄檔可能外洩欄位、對照台灣《個人資料保護法》（下稱「個資法」）一般要求之缺口與建議
- **性質：** 本目錄僅為**盤點報告與建議**，未修改任何原始碼；所有建議需另行開分支實作。
- **repo：** YourheroBOB/desktop-harness @ v0.4.2
- **法律免責：** 本文為工程師視角的一般性對照，**不是法律意見**；涉及實際蒐集/利用個人資料的營運決策，應諮詢律師。

## 重要前提：本工具的個資風險本質

desktop-harness 是**通用桌面控制工具**，本身不設計來「蒐集特定當事人資料」；但它的核心能力（AX 樹讀取、視窗／全螢幕截圖、鍵盤輸入、agent 腳本任意 exec）使它**必然接觸使用者螢幕上的一切內容**。若使用者（例如 BOB）在執行業務（如律師工作、客戶往來、LINE 對話）時以本工具驅動 agent，則螢幕上的文件、訊息、當事人姓名等即可能成為「被處理的個人資料」，且會隨 agent 的 stdout／截圖**跨境送往 AI 模型服務商**。這是本盤點最重要的視角。

## 檔案索引

| 檔案 | 內容 |
|------|------|
| [licenses.md](./licenses.md) | 相依套件授權清單與相容性結論 |
| [personal-data-inventory.md](./personal-data-inventory.md) | 個人資料類別與流向盤點（資料地圖） |
| [retention-and-deletion.md](./retention-and-deletion.md) | 保存與刪除機制現況 |
| [logs-and-leakage.md](./logs-and-leakage.md) | 記錄檔與輸出中可能外洩的欄位 |
| [pdpa-gap-analysis.md](./pdpa-gap-analysis.md) | 對照台灣個資法的缺口（COMP-1～COMP-10）與建議 |

## 盤點限制

- 以下檔案未在本次工作樹視野內，涉及之推論標記「待確認」：`helpers.py`、`ax.py`、`input.py`、`run.py`、`presence.py`、`daemon.py`、`selftest.py`、`voice_tools.py`、`windows.py` 的完整實作內容。行為引用 `docs/PRE-RELEASE-REVIEW.md`、`docs/fmb-perf/`、ADR 既有發現交叉確認。
- 相依套件授權以 PyPI 上游慣常授權為準（repo 內無 lockfile／SBOM，版本未釘選，見 licenses.md 之 COMP-7）。
- 本盤點**不含**任何真實個資、憑證、訊息內文或案件資料；所有範例皆為虛構。

## 撰寫原則

1. 只描述 repo 內可驗證的事實，推論標明。
2. 不複製任何敏感字串、token 或訊息內容。
3. 建議以「最小變更、最保守」為方向，供 BOB 決策。
