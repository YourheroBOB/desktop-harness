# desktop-harness 相依升級風險評估

**狀態：** 文件提案，未實際修改或升級。  
**嚴重度定義：** P0 主要功能失效或安全模型受損；P1 正確性／可靠性／供應鏈明顯風險；P2 打磨項或文件／打包衛生。

---

## 1. 風險總表

| ID | 項目 | 風險描述 | 嚴重度 | 建議處理階段 |
|----|------|----------|--------|--------------|
| DEP-1 | pyobjc 三個核心相依完全未鎖版本 | 安裝結果隨發布版漂移；上游可能提高 Python/macOS 最低需求或调整 API 行為 | **P1** | Phase 1、Phase 3 |
| DEP-2 | Python `>=3.10` 且無支援矩陣 | Python 3.10 已接近上游 EOL；只測 3.10 容易漏掉新版相容性 | **P1** | Phase 2 |
| DEP-3 | 無 lockfile / constraints | `install.sh` 每次安裝可能拿到不同版本，無法重現 | **P1** | Phase 1 |
| DEP-4 | `hatchling` 未鎖版本 | build backend 可能改變 wheel metadata、entry point、`force-include` 行為 | P2 | Phase 6 |
| DEP-5 | voice extras 未宣告 | `websockets`、`sounddevice`、`numpy` 由文件手動安裝，binary wheel 易漂移 | P2 | Phase 5 |
| DEP-6 | macOS AX / CGEvent / AppKit 耦合 | pyobjc 或 Python 升級可能影響 `ax_snapshot`、`click_text`、`screenshot`、presence overlay | **P1** | Phase 3、Phase 4 |
| DEP-7 | warm daemon 版本漂移 | 升級 CLI/套件後，舊 daemon 可能仍持有舊模組；socket/token/pid 可能 stale | **P1** | Phase 4 |
| DEP-8 | `selftest` / `demo` 有全域副作用 | `selftest` 會開 TextEdit、移動滑鼠、操作 daemon；`demo.py` 找不到 TextEdit 時仍有打字風險 | P2 | Phase 3、Phase 7 |
| DEP-9 | 無 pytest 設定與自動化測試地基 | 難以在多人環境重複驗證；場景化測試缺地基 | P2 | Phase 1 |
| DEP-10 | voice `--dry-run` 語意與 secret 文件風險 | 現行 `--dry-run` 可能執行真實 GUI；文件曾鼓勵把 key 寫在命令列 | P2 | Phase 5 |
| DEP-11 | 打包 metadata 不完整 | 無 license metadata；`SKILL.md` 雙份真相可能漂移 | P2 | Phase 1、Phase 6 |
| DEP-12 | repo URL 文件不一致 | README／install 文件出現非本 repo 的 GitHub URL，可能造成 clone 來源混淆 | P2 | Phase 7 前由 BOB 決策 |

---

## 2. 相容性風險細節

### 2.1 pyobjc 核心相依

pyobjc 是 desktop-harness 的核心執行基礎。升級時需關注：

- `Quartz`：`CGWindowListCreateImage`、`CGEventPost`、`CGWarpMouseCursorPosition` 行為。
- `Cocoa`：`NSWorkspace`、`NSRunningApplication`、`NSBitmapImageRep` 與 presence AppKit overlay。
- `ApplicationServices`：`AXIsProcessTrusted`、AX tree walk、`AXPress`、`AXSetAttributeValue`。

pyobjc 套件之間通常有版本耦合，單獨升級一個 framework 可能觸發 transitive dependency 變更。因此建議一次只升一個主題，並以 `pip check` 與實機功能驗證把關。

### 2.2 Python 版本

目前 `requires-python = ">=3.10"`，未宣告上限。升級時需確認：

- 3.10、3.11、3.12 是否都能安裝所選 pyobjc 版本。
- binary wheel 是否都有對應 Python tag。
- 是否需要在 3.10 EOL 後提高最低版本。

保守預設：本輪先維持 `>=3.10`，但補支援矩陣；是否提高到 `>=3.11` 或 `>=3.12` 需 BOB 決策。

### 2.3 warm daemon

daemon 是「本機特權 exec 端點」。升級時不得降低安全屬性：

- socket 與 token 必須維持 0600。
- 不接受未帶正確 token 的 exec 請求。
- 不得把 token 寫入 log、stdout、stderr、文件或測試輸出。
- 測試一律使用暫存 `DH_SOCKET`、`DH_TOKEN_PATH`、`DH_AUDIT_LOG`。

### 2.4 實驗性 voice

voice 路徑不是核心安裝路徑，但牽涉：

- 外部 WebSocket 服務。
- 麥克風權限。
- 潛在敏感語音內容與工具參數。

因此驗證必須離線化，不得連線正式 realtime 服務；需要假金鑰時使用 `FAKE_VALUE_FOR_TEST`。

---

## 3. 現有審查報告交叉參考

| 現有 finding | 對本計畫的意義 |
|--------------|----------------|
| PKG-1 | pyobjc 未鎖下限，是 Phase 1／Phase 3 主因 |
| PKG-2 | license metadata 應在打包階段補齊 |
| PKG-3 | voice extras 應在 Phase 5 宣告 |
| PKG-4 | `SKILL.md` 雙份真相需在打包驗證確認 |
| PKG-5 | pytest 設定是自動化驗證地基 |
| INS-3 / LAU-3 | 缺少 macOS / Python preflight |
| VS-1 | voice `--dry-run` 未修正前不應作為驗證工具 |
| DOC-1 | repo URL 不一致會影響安裝來源可信度 |
| DAEMON-1 / DAEMON-2 | daemon 升級前需確認沒有回退到已知 P0 行為 |

---

## 4. 風險接受原則

- 不接受「可能把按鍵打進未知前景 app」的自動化驗證。
- 不接受「為了升級而連線正式 voice 服務」的驗證。
- 不接受「在使用者預設 daemon 路徑上直接測試」。
- 不接受「同一個 PR 同時升級 Python、pyobjc、hatchling、voice extras」。
- 若某個 pyobjc 新版本需要新版 Python 或新版 macOS，優先選擇仍相容的舊版，而不是直接提高最低系統需求。
