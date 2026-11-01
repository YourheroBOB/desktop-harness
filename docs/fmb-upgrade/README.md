# desktop-harness 相依套件升級計畫（docs/fmb-upgrade）

**狀態：** 提案（proposal only）  
**範圍基準：** `YourheroBOB/desktop-harness` @ `v0.4.2` 快照  
**本目錄性質：** 只新增文件；未修改任何程式碼、`pyproject.toml`、`install.sh`、workflows、secrets；未實際升級任何相依套件。

---

## 目標

1. 盤點 desktop-harness 的語言版本、Python 相依、建置系統與執行環境。
2. 評估過時、未鎖版本、已知相容性風險與供應鏈風險。
3. 提出可分批執行的升級計畫，每一步包含：
   - 變更內容
   - 相容性風險
   - 驗證方式
   - 回滾方式
4. 所有驗證都必須可在不連線正式服務、不读写 repo 外路徑、不洩漏憑證的前提下執行。

---

## 硬性護欄（所有階段都適用）

- 不 `git push`、不 merge、不修改 git remote、不刪分支。
- 不修改 `.github/workflows` 與任何 secrets／憑證設定。
- 不將 token、金鑰、密碼、客戶個資、LINE 訊息內文、案件當事人資料寫入任何文件。
- 測試需要假憑證時，一律使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串。
- 不連線任何網路正式服務；voice 相關驗證用本地 mock WebSocket 或修正後的 `--dry-run`。
- 不讀寫 repo 外路徑；臨時檔案使用 `tempfile` / `tmp_path`。
- 不影響使用者目前正在執行的 daemon；daemon 驗證使用 `DH_SOCKET`、`DH_TOKEN_PATH`、`DH_AUDIT_LOG` 指向暫存目錄。
- 本計畫不進行靜默自動更新；實際安裝／升級一律由使用者手動觸發。

---

## 文件索引

| 檔案 | 內容 |
|------|------|
| [inventory.md](./inventory.md) | 語言版本、相依套件、建置系統、執行環境與文件證據盤點 |
| [risk-assessment.md](./risk-assessment.md) | 過時／未鎖版本／已知風險評估與對應階段 |
| [upgrade-plan.md](./upgrade-plan.md) | 分階段升級計畫、驗證方式與回滾方式 |

---

## 建議執行順序

```text
Phase 0 基線與環境 snapshot
  → Phase 1 打包衛生與 preflight
  → Phase 2 Python 支援矩陣
  → Phase 3 pyobjc 核心相依升級
  → Phase 4 warm daemon 相容性驗證
  → Phase 5 實驗性 voice 相依 extras
  → Phase 6 建置系統與可重現打包
  → Phase 7 Canary 發佈與監控
```

每個 Phase 都應可獨立 revert；不建議把 Python、pyobjc、hatchling、voice extras 放在同一個 PR。
