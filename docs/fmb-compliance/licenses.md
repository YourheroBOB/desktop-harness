# 相依套件授權盤點與相容性結論

> 本盤點基於 `pyproject.toml`、`install.sh`、`install.md`、`VOICE.md` 與 `LICENSE`。repo 內**無 lockfile、無 SBOM、無 CI 供應鏈掃描**，套件版本完全未釘選（`pyobjc-framework-*` 皆無版本約束），授權結論以 PyPI 上游慣常授權為準。

## 1. 專案本身

| 項目 | 內容 |
|------|------|
| License | MIT（`LICENSE` 檔，Copyright (c) 2026 freeze / xfreeze2） |
| 授權義務 | 重散布時保留版權與許可聲明 |

**觀察（非本次修改）：**
- `LICENSE` 著作權人為「freeze / xfreeze2」，而 repo 位於 `YourheroBOB/desktop-harness`、`RELEASE.md`／`README.md` 提及 push 至 `xfreeze2/desktop-harness`。**授權人名稱與實際 repo 擁有者的對應關係需要 BOB 確認**（fork／授權關係或名稱變更），以免日後宣稱授權時有瑕疵。
- repo 為私有 repo 且對外宣稱 MIT：若未來公開，需確認無任何貢獻者授權爭議。

## 2. 執行期相依（pyproject.toml `dependencies`）

| 套件 | 授權（上游慣常） | 與 MIT 相容 | 用途 |
|------|------------------|--------------|------|
| `pyobjc-framework-Quartz` | MIT | ✅（同為 MIT，義務相同：保留聲明） | CGWindowList、CGEvent、截圖 |
| `pyobjc-framework-Cocoa` | MIT | ✅ | NSWorkspace、NSBitmapImageRep、presence overlay |
| `pyobjc-framework-ApplicationServices` | MIT | ✅ | AX API、`AXIsProcessTrusted` |

**結論：執行期相依全為 MIT，與本專案 MIT 完全相容，無義務衝突、無 copyleft 風險。**

注意事項：
- pyobjc 套件捆綁的 Apple framework bridge 只在 macOS 系統上運作；**呼叫的是 Apple 系統框架**（本地 runtime 連結），不構成 Apple 授權條款的重散布議題，僅需留意 Apple SDK 條款不允許將 Apple 軟體重散布到非 Apple 硬體——本工具本就限 macOS，無此風險。
- pyobjc 慣常授權 MIT 以 PyPI metadata 為準；建議落地 `pip-licenses` 或 `pip install --dry-run --report` 產出正式授權清單存證（見 pdpa-gap-analysis.md COMP-7）。

## 3. 建置相依（build-system）

| 套件 | 授權 | 角度 |
|------|------|------|
| `hatchling` | BSD-3-Clause | 僅建置期相依，不進入 wheel、不隨本專案重散布 |

BSD-3-Clause 與 MIT 相容；因 hatchling 不被散布給終端使用者（終端以 `pip install -e .` 自行拉取建置），無義務轉嫁問題。若以 binary wheel 對外發布，仍只需遵守本專案 MIT 即可。

## 4. 選用／實驗性相依（未列入 pyproject，依 `VOICE.md`／`voice_session.py` 臨時安裝）

| 套件 | 授權（上游慣常） | 相容 | 備註 |
|------|------------------|------|------|
| `websockets` | BSD-3-Clause | ✅ | 僅 voice 實驗路徑需要 |
| `sounddevice` | MIT | ✅ | 麥克風 PCM |
| `numpy` | BSD-3-Clause | ✅ | 音訊處理 |

**結論：相容。** 但這些套件**未宣告於 `pyproject.toml`**（`pip install websockets sounddevice numpy` 手動裝），導致授權盤點無法從 metadata 重現——與 COMP-7 一併處理：將實驗性 voice 相依移入 optional extras（如 `[project.optional-dependencies] voice = [...]`）並釘版本。

## 5. 未使用的相依

無。`pyproject.toml` 宣告的三個執行期相依與程式用途一一對應，沒有孤兒相依。測試框架（pytest 等）未宣告——目前 repo 無自動化測試套件（selftest 為 runtime 自測）。

## 6. 總結論

- **授權相容性：無缺口。** 所有相依皆為寬鬆授權（MIT／BSD-3），MIT 專案可自由重散布，義務僅為保留聲明。
- **程序性缺口（非授權本身）：**
  1. 無 lockfile → 供應鏈重現性為零，授權／資安掃描無法固定基準（COMP-7）。
  2. `LICENSE` 著作權人與 repo 擁有者對應需 BOB 確認。
  3. voice 選用相依未進 metadata，正式盤點時會漏掉。
  4. 無 `THIRD_PARTY_NOTICES`／`pip-licenses` 產物；建議 release checklist（`RELEASE.md`）加一條「產出相依授權清單」。
