# desktop-harness CI / 品質關卡提案（docs/fmb-ci）

- **日期：** 2026-08
- **性質：** 提案與可直接採用的設定範本。**本目錄只新增文件，未建立任何 workflow 檔、未修改 `.github/`。**
- **repo：** YourheroBOB/desktop-harness @ v0.4.2

## 為什麼需要 CI

這個專案的特殊性讓 CI 特別重要：

1. **它控制真實 Mac**——能動滑鼠鍵盤的程式碼，每次變更都值得被機器把關（RELEASE.md 的 "no silent auto-update" 精神：變更要被審視才能出）。
2. **歷史事故都發生在「回傳成功 ≠ 實際成功」的縫隙**（media postmortem、presence bug）——自動化測試是提早抓這類迴歸的唯一手段。
3. **安全宣稱必須與實作一致**（PRE-RELEASE-REVIEW #1 的教訓）——`safety.py` 的 gate 邏輯是純 Python，完全可以單元測試。
4. **pyobjc / macOS 相依**讓「在我機器上能跑」與「在任何 Mac 上能跑」有落差——建置關卡保證 wheel 一直可安裝。

## 設計原則（本提案的硬性邊界）

| 原則 | 理由 |
|------|------|
| CI **絕不**跑 `selftest` / `demo` 的 GUI 部分 | 那需要 Accessibility + Screen Recording 權限與人眼監看；GitHub runner 給不了，也不該給 |
| CI 測試**不觸任何網路正式服務** | 呼應 `docs/fmb-perf/verification-plan.md`：voice 全走假 server / dry-run |
| CI 測試**不讀寫 repo 外路徑** | 一律 `tmp_path` / `tempfile` 沙箱 |
| 假憑證一律 `FAKE_VALUE_FOR_TEST` | 絕不使用 `sk-` 等真實格式前綴 |
| 不引入任何 token / secrets 到 repo | 掃描關卡本身就是防這件事的 |

## 關卡總覽

```
PR / push
  ├── L1  lint（ruff）＋型別（mypy，漸進式）
  ├── L2  單元測試（pytest，沙箱）＋覆蓋率報告（初期不設門檻）
  ├── L3  秘密掃描（gitleaks）＋相依掃描（pip-audit）
  ├── L4  建置（wheel + sdist，驗證 SKILL.md 已打包）
  └── L5  安裝煙霧測試（fresh venv → pip install wheel → --version/--help/--doctor 的無 GUI 部分）

tag v*
  └── L6  發佈關卡（人工觸發 → 重跑 L1–L5 → 上傳 artifact，發佈動作本身建議手動）
```

詳細設計與範本：

| 文件 | 內容 |
|------|------|
| [QUALITY-GATES.md](./QUALITY-GATES.md) | lint / 型別 / 測試 / 覆蓋率：設計、工具選擇、YAML 範本、`pyproject.toml` 設定片段 |
| [SECURITY-SCANS.md](./SECURITY-SCANS.md) | 秘密掃描、相依漏洞掃描、ShellCheck（install.sh）：範本與理由 |
| [BUILD-RELEASE.md](./BUILD-RELEASE.md) | 建置驗證、安裝煙霧、發佈關卡與 RELEASE.md 清單的自動化對照 |

## macOS runner 的成本現實（決策點）

本專案**必須**用 macOS runner（pyobjc 無法在 Linux 上 import）。GitHub 對私有 repo 的 macOS runner 計費是 Linux 的 **10 倍**（2026 年現況）。因此本提案：

- **只保留一個 macOS job**，把 lint / 型別 / 掃描 / 建置全部塞進同一個矩陣的單一節點，而不是每個關卡開獨立 job。
- Linux 上能跑的部分（ruff、mypy 的純語法部分、gitleaks、pip-audit 對 metadata 的掃描）用 `ubuntu-latest` 省錢——但要保守：**import 級測試與建置必須在 macOS**，Linux 上 pip-audit 裝不了 pyobjc 時只掃 metadata。
- 若 BOB 認為成本可接受，可拆成多 job 提高失敗訊號的清晰度（見各文件的「拆分選項」）。

## 目前 repo 現況誠實條目

- **沒有任何 pytest 測試**：`selftest` 是 GUI 端到端、需要權限，不能當 CI 測試。因此 L2 初期只能跑「import + CLI smoke + 少量新增的純邏輯測試」——建議第一個 PR 就補上 `safety.py` 的 gate 測試與 `windows.find_app` 匹配排序測試（純函式、易 mock）。
- **`pyproject.toml` 沒有任何 lint / type / pytest 設定**——QUALITY-GATES.md 附可直接貼上的片段。
- **`install.sh` 有 shell 邏輯**——SECURITY-SCANS.md 附 ShellCheck。
- **已知的版本一致性問題**（review #3 的歷史）：建議 L4 加一個「`__init__.py` 的 `__version__` 必須等於 `pyproject.toml` 的 `version`」檢查——這正是過去真實出過的錯。
