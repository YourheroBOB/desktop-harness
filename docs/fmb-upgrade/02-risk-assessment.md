# 02 · 風險評估：過時與已知風險項目

> 依嚴重度排序。嚴重度定義：**高** = 可能導致功能壞掉或安全風險；**中** = 維護性／可重現性問題；**低** = 打磨項目。

## R1（高）· 相依完全未鎖版本，且無 lock 檔

- **現況：** pyobjc 三套件 + hatchling 全部浮動；無 requirements lock、無 CI。
- **風險：** 任何新機器安裝、或既有使用者跑 `install.sh` 更新，都可能拉進**未經測試的新版 pyobjc**。pyobjc 是直接 bridge 系統 framework 的套件，新版常伴隨 macOS SDK 對齊而改變行為；一旦壞掉，症狀會是 AX 快照失敗、CGEvent 無效、presence overlay 崩潰——正好是本工具的核心路徑。
- **評估：** 這是清單中唯一「不做任何升級也隨時可能爆炸」的項目，列為第一優先。

## R2（高）· `requires-python` 無上界

- **現況：** `>=3.10`。
- **風險：** Python 3.13/3.14 陸續移除舊標準庫模組、改變預設行為。本 repo 未用已移除模組（檢查過 import：`json/os/socket/secrets/traceback/tempfile/pathlib/asyncio/argparse`，皆為穩定 API），但 pyobjc 對新 Python 的支援永遠落後一拍——**在新 Python 上 pip 會找到「宣稱相容但其實還沒驗證」的 pyobjc**。
- **評估：** 應加上經過測試的上界（例如 `>=3.10,<3.13`，於驗證後放寬），並在 install.sh 固定 venv 使用的解譯器版本。

## R3（高）· 無測試套件、無 CI → 升級無安全網

- **現況：** 驗證只有 `--doctor`／`selftest`／`demo`，全部需要真機 Accessibility + Screen Recording 權限與真人觀看（demo 會動滑鼠、開 TextEdit）。
- **風險：** 升級 pyobjc 後沒有任何自動化方式判斷「AX walk、點擊、截圖」是否還正常；回滾判斷只能靠人工。
- **評估：** 升級計畫的第一階段必須先補最小測試層（純邏輯單元測試：`safety.py` 的 sensitive 判斷、`windows.find_app` 的排序邏輯（需 mock）、`voice_tools` 的 JSON 解析錯誤路徑、daemon 的 token 驗證），這些不需要 GUI 權限，可直接在 CI/本地跑。

## R4（中）· `ax.py` 依賴 magic type int，pyobjc 升級的放大器

- **現況：** PRE-RELEASE-REVIEW #14 指出 `_ax_point` 用 `1`/`2` 而非 `kAXValueCGPointType`/`kAXValueCGSizeType` 常數。
- **風險：** magic int 是「碰巧等於目前 pyobjc 常數值」。pyobjc 未來版本若改變底層列舉表示，此處會**安靜地產生錯座標**而非拋錯——比崩潰更危險。
- **評估：** 列為升級前置必改項（程式碼小改動，風險低），在 pin 版本前先修，避免把隱性地雷鎖進「驗證通過」的版本組合裡。

## R5（中）· voice 相依未宣告、未分組

- **現況：** `websockets` 由執行期 import 失敗訊息提示手動安裝；`sounddevice`/`numpy` 只存在於文件。
- **風險：** 語音功能形同不可安裝（無法一鍵裝齊）；未來有人幫 voice 裝新版 `websockets`（API 曾有 breaking change：`additional_headers` 參數即為新版 API，舊版用 `extra_headers`）時，`voice_session.py` 會直接 AttributeError。
- **評估：** 補 `[project.optional-dependencies] voice = [...]` 並 pin。屬中風險，因 voice 明確標示為實驗性、非核心路徑。

## R6（中）· 系統外部指令隨 macOS 升級漂移

- **現況：** `open`、`osascript`、`screencapture`（`selftest`、`observe-demo.sh`、`windows.activate`）。
- **風險：** macOS 大版本更新 historically 曾改變 AppleScript 用語與權限提示行為；`osascript -e 'tell application "TextEdit" to activate'` 這類呼叫在新系統可能觸發新的權限對話框，導致 selftest 掛掉但與 pip 相依無關。
- **評估：** 不屬於 pip 升級範圍，但**升級驗證清單必須包含 macOS 小版本更新後重跑 selftest**，否則會誤判為套件問題。

## R7（低）· hatchling 未鎖版

- **風險：** 建置期才解析，最壞情況是 `pip install -e .` 失敗，不影響已部署安裝。
- **評估：** 與 R1 一併處理即可。

## R8（低）· daemon exec namespace 與 agent_helpers 熱載

- **現況：** `agent-workspace/agent_helpers.py` 於 daemon 啟動時載入一次（review #16）。
- **風險：** 升級後若使用者忘記 `daemon stop`，舊 daemon process 會繼續跑**舊程式碼 + 舊 pyobjc**，讓「已升級已驗證」判斷失真。
- **評估：** 升級流程必須把「daemon stop → 升級 → daemon start」列為強制步驟（見計畫各階段的回滾／驗證段）。

## 風險總表

| # | 項目 | 嚴重度 | 處理階段 |
|---|------|--------|----------|
| R1 | 相依未鎖版／無 lock | 高 | Phase 0 |
| R2 | Python 版本無上界 | 高 | Phase 1 |
| R3 | 無測試／無 CI | 高 | Phase 0（先補測試再升級） |
| R4 | AX magic int 常數 | 中 | Phase 0（前置程式修正） |
| R5 | voice 相依未宣告 | 中 | Phase 2 |
| R6 | 系統指令隨 macOS 漂移 | 中 | 各階段驗證清單 |
| R7 | hatchling 未鎖 | 低 | Phase 0 |
| R8 | 舊 daemon 殘留 | 低 | 各階段流程步驟 |
