# desktop-harness 相依套件升級計畫（總覽）

> 本目錄為「相依套件與執行環境升級計畫」文件，**僅為規劃文件，不包含任何實際升級動作**。
> 建立日期：2026-08-12 · 對應版本：desktop-harness v0.4.2

## 文件清單

| 檔案 | 內容 |
|------|------|
| [01-inventory.md](./01-inventory.md) | 語言版本、相依套件、執行環境盤點 |
| [02-risk-assessment.md](./02-risk-assessment.md) | 過時／已知風險項目評估 |
| [03-upgrade-plan.md](./03-upgrade-plan.md) | 分階段升級計畫（變更、風險、驗證、回滾） |

## 一句話結論

目前最大的風險不是「套件太舊」，而是**所有相依都未鎖版本**（pyobjc 三個 framework 完全浮動、無 lock 檔、無 CI、無測試套件），任何一次 `install.sh` 重跑都可能拉到不相容的新版 pyobjc 而壞掉。升級計畫以「先建立可重現性，再談升級」為原則。

## 重要前提

- 本 repo **沒有測試套件**（無 pytest、無 tests/ 目錄），驗證只能靠 `desktop-harness --doctor`、`desktop-harness selftest`、`desktop-harness demo` 三個內建指令。
- 本 repo **沒有 `.github/workflows`**，無 CI 可依賴，所有驗證需在本地 Mac 手動執行。
- pyobjc 與 macOS 版本強耦合（bridge 到系統 framework），升級決策必須以「目標機的 macOS 版本」為錨，不能只看 PyPI 版號。
