# 03 · 分階段升級計畫

> 原則：**先建立可重現性與測試安全網，再進行任何實際升級**。每個階段獨立可驗證、獨立可回滾；上一階段未通過驗證不進入下一階段。本文件僅為計畫，不執行。

## 共通前置（每階段都要做）

1. `desktop-harness daemon stop`（避免 R8：舊 daemon 熱程式碼干擾驗證）。
2. 記錄目前狀態：`pip freeze > /tmp/dh-before-<phase>.txt`（放 repo 外，避免把環境細節寫進 git）。
3. 在專屬分支上作業，每階段一個 commit，方便 `git revert` 單階段回滾。

## 共通驗證（每階段結束必跑，依序）

| 步驟 | 指令 | 需要什麼 |
|------|------|----------|
| 1. 套件層 | `python -m desktop_harness.run --version`、`import desktop_harness` | 無需權限 |
| 2. 醫生 | `desktop-harness --doctor` | Accessibility + Screen Recording |
| 3. 自測 | `desktop-harness selftest` | 同上；會開 TextEdit 並打字（非破壞性） |
| 4. 視覺煙霧 | `desktop-harness demo` | 真人觀看滑鼠移動與 presence ring |
| 5. daemon | `desktop-harness daemon start --bg` → `exec_via_daemon` roundtrip → `daemon stop` | 同 2 |

（selftest 內含 doctor 與 daemon roundtrip，但分開跑可定位失敗層。）

---

## Phase 0 · 建立可重現基準（不改任何執行版本）

**目標：** 把「現在做一次乾淨安裝會裝到什麼」固定下來，並補最小測試。**此階段不升級任何套件，只鎖住現狀。**

### 變更內容

1. 在目標機跑 `pip freeze`，記下 pyobjc 三套件與 hatchling 目前實際版本 `X.Y.Z`。
2. `pyproject.toml`：把三個 pyobjc 相依改為 `~=` 相容性約束（例如 `pyobjc-framework-Quartz~=X.Y`），hatchling 同樣處理。
3. 產出鎖定檔（保守做法：`requirements-lock.txt`，由 `pip freeze` 生成並提交；不引入 uv/pip-tools 等新工具鏈，維持最小變更）。
4. 新增 `tests/` 最小單元測試（不需 GUI 權限、不需網路、讀寫只用 `tmp_path`）：
   - `safety._looks_sensitive`／`check_app_allowed` 的正向與阻擋案例（app 名稱用假字串如 `"FakeWalletApp"`）
   - `voice_tools.execute` 對非法 JSON arguments 的錯誤路徑（用 `FAKE_VALUE_FOR_TEST` 類假字串）
   - `daemon` token 驗證邏輯（token 一律用 `"FAKE_VALUE_FOR_TEST"`，socket 測試用 `tmp_path` 下的暫存路徑）
   - `windows.find_app` 的排序規則（mock `list_apps`）
5. `install.sh`：改為從 lock 檔安裝（`pip install -r requirements-lock.txt`），保留 venv 流程不動。
6. 前置程式修正（R4）：`ax.py` magic int `1`/`2` 換成 `kAXValueCGPointType`/`kAXValueCGSizeType` 常數——這是行為等價修正，但**必須**在此階段完成，讓 Phase 1 的驗證對象是乾淨的程式碼。

### 相容性風險

- 低。`~=` 約束允許現有版本繼續安裝，不改變任何執行中的程式碼路徑（除 R4 修正，其等價性由 selftest 的 AX snapshot 步驟驗證）。
- lock 檔與 `pyproject.toml` 宣告需保持同步，否則未來會漂移——在計畫中列為維護規則。

### 驗證方式

- 共通驗證 1–5 全跑。
- `pip install -r requirements-lock.txt && pip install -e . --no-deps` 於全新 venv 重做一次，比對 `pip freeze` 與 lock 檔一致。
- 新單元測試全綠（可用 `python -m pytest tests/ -q`；pytest 需加入 optional dev 相依）。

### 回滾方式

- `git revert` 該分支 commit；`rm -rf .venv && ./install.sh` 重建原環境（原相依本來就未鎖，回滾後行為與今日相同）。

---

## Phase 1 · Python 與 pyobjc 版本治理（第一次真正的「升級」）

**目標：** 給 `requires-python` 設上界、在 venv 中固定解譯器、把 pyobjc 對齊到「目標機 macOS 版本對應的最新穩定版」。

### 變更內容

1. 於目標機確認 macOS 版本與 `python3` 版本；選定一個**已驗證**的 Python（保守建議：目前可用的最新 3.11 或 3.12，避免 3.13+ 直至 pyobjc 官方宣稱支援）。
2. `pyproject.toml`：`requires-python = ">=3.10,<3.13"`（上界依 Phase 1 實測結果決定，實測通過 3.13 再放寬）。
3. `install.sh`：venv 建立前檢查 `python3 --version` 落在支援區間，不符合即明確報錯（而非安裝出壞環境）。
4. 評估 pyobjc 是否升級：查 PyPI 上三個 framework 對應目標 macOS 的最新版本；**若目前版本已支援目標 macOS，則本階段只鎖不升**（保守決策）；若目標機是新版 macOS 而 pyobjc 舊版有已知不相容，才升到修復版本。
5. 更新 `install.md` 的 Requirements 段落反映實測結果（例如「macOS Sequoia 15.x 實測通過」）。

### 相容性風險

- **pyobjc 跨版本**：常數列舉值改變、橋接型別 init 行為差異 → 症狀集中在 `ax.py`（座標錯）、`capture.py`（PNG 編碼）、`presence`（AppKit 視窗屬性）。R4 已在 Phase 0 消除最大隱患。
- **Python 次要版本**：本 repo 未用冷門 API，風險低；主要風險在 pyobjc 對該 Python 的輪子可用性（Apple Silicon / Intel 需分別確認）。
- **`<3.13` 上界**：對已用 3.13 的使用者會變成安裝失敗——這是刻意行為（明確失敗優於安靜壞掉），需在 install.md 註明。

### 驗證方式

- 共通驗證 1–5 於**目標 macOS + 選定 Python** 組合上全跑。
- 額外：`desktop-harness <<'PY' ... PY` 跑一個多步驟腳本（move → click → labels → screenshot），確認座標系與 AX 路徑在 daemon 冷/熱兩種模式下結果一致。
- 若升級了 pyobjc：在**第二台不同 macOS 版本的機器**（若有）重跑共通驗證，確認沒有綁死單一系統版本。

### 回滾方式

- 相依層：`pip install -r requirements-lock.txt`（Phase 0 的 lock 即是回滾點）。
- 程式層：`git revert` 該 commit。
- 環境層：刪 venv 重跑 install.sh（install.sh 本身的變更也會被 revert，回到原本行為）。

---

## Phase 2 · 可選相依（voice）宣告與鎖定

**目標：** 讓實驗性 voice 路徑可一鍵安裝、可重現，且不污染核心安裝。

### 變更內容

1. `pyproject.toml` 新增：
   ```toml
   [project.optional-dependencies]
   voice = ["websockets~=W.Y", "sounddevice~=W.Y", "numpy~=W.Y"]  # 以 Phase 2 當時實測版本填入
   dev = ["pytest~=W.Y"]  # Phase 0 引入的測試所需
   ```
2. 產出對應 lock（保守：單一 requirements-lock.txt 附註解分段，或第二個 `requirements-voice-lock.txt`）。
3. `install.md`／`VOICE.md` 補上 `pip install -e ".[voice]"` 安裝說明，維持「voice 為選用實驗性」的定位。
4. `voice_session.py` 的 `websockets` API 用法（`additional_headers`）寫進驗證清單——新版 websockets 的參數名需與鎖定版本核對。

### 相容性風險

- voice 依賴網路（`wss://api.x.ai`），**驗證時不得連正式服務**；僅驗證 `--dry-run`、`--list-tools`、`--text` 模式的本地行為與錯誤訊息（無 `XAI_API_KEY` 時應出現提示並 exit 2）。
- `sounddevice` 需要 PortAudio 系統庫，可能觸發額外安裝——保持它只在明確要求時安裝（optional group 已做到）。

### 驗證方式

- `pip install -e ".[voice]"` 於全新 venv 成功；`python scripts/voice_session.py --list-tools` 列出工具；無 key 時 `--dry-run --text` 走本地工具 demo 且**不發網路請求**。
- 核心路徑回歸：共通驗證 1–3（確認 optional 群組沒有影響主安裝）。

### 回滾方式

- `git revert`；`pip uninstall websockets sounddevice numpy` 或直接重建 venv（voice 套件本來就是手動裝的，回滾無痛）。

---

## Phase 3 ·（選配，需 BOB 決策）工具鏈現代化

**目標：** 把可重現性從「pip freeze 檔」升級到正式工具。**此階段效益是維護性，不是功能，優先級最低。**

### 候選變更

| 選項 | 內容 | 取捨 |
|------|------|------|
| A. uv | 以 `uv` 管理 venv + `uv.lock` 取代 pip freeze | lock 品質最好、跨平台；代價是引入新工具、install.sh 改寫 |
| B. ruff | 取代手動清理 import（review #24 的 dead imports） | 低風險、快速 |
| C. GitHub Actions CI | 跑 Phase 0 的單元測試（無 GUI 權限的部分） | 讓 R3 安全網自動化；需動 workflows（本任務範圍外，另案處理） |

### 風險與驗證、回滾

- 依選項各別評估；共同原則：**不改變已鎖定的套件版本集合**（Phase 3 只換「怎麼裝」，不換「裝什麼」），因此驗證只需證明 lock 等價 + 共通驗證 1–3。
- 回滾：`git revert`，回到 Phase 0/2 的 lock 檔流程。

---

## 執行順序與時間安排建議

```
Phase 0（鎖版 + 補測試）── 必做，是其他一切的前提
   └─ Phase 1（Python/pyobjc 治理）── 必做
        └─ Phase 2（voice 選用相依）── 建議做
             └─ Phase 3（工具鏈現代化）── 選配，BOB 決策
```

每階段之間保留至少一個工作日的實際使用觀察期（agent 日常使用中若 AX／滑鼠行為異常，會在這段時間浮現），再進入下一階段。
