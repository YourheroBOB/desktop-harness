# desktop-harness 相依與執行環境盤點

**狀態：** 文件提案，未實際修改或升級。  
**主要證據：** `pyproject.toml`、`install.sh`、`desktop-harness`、`install.md`、`README.md`、`DESIGN.md`、`docs/fmb/ARCHITECTURE*.md`、`docs/fmb-review/README.md`、`docs/fmb-perf/README.md`。

---

## 1. 語言版本

| 項目 | 目前宣告 | 證據 | 初步評估 |
|------|----------|------|----------|
| Python 最低版本 | `>=3.10` | `pyproject.toml` | 可支援 3.10，但 3.10 已接近上游 EOL；需評估是否長期維持 |
| Python 最高版本 | 未宣告 | `pyproject.toml` | 建議補支援矩陣，避免只測最低版本 |
| 執行 Python | `python3` | `install.sh`、`desktop-harness` | macOS 系統或 Homebrew Python 可能不同；需要 preflight |
| venv | `.venv` | `install.sh`、`desktop-harness` | 已有本地 venv 模式，但未鎖定解析結果 |

---

## 2. Python 相依套件

| 套件 | 用途 | 目前版本宣告 | 風險 |
|------|------|--------------|------|
| `pyobjc-framework-Quartz` | CGWindowList、CGEvent、截圖、螢幕邊界 | 無下限、無上限 | 新版本可能改變 API 或提高 Python/macOS 需求 |
| `pyobjc-framework-Cocoa` | NSWorkspace、NSRunningApplication、NSBitmapImageRep、presence AppKit overlay | 無下限、無上限 | AppKit 行為對 macOS 版本敏感 |
| `pyobjc-framework-ApplicationServices` | `AXIsProcessTrusted`、Accessibility API | 無下限、無上限 | AX 行為會影響主要功能 |
| `hatchling` | build backend | `build-system.requires` 未鎖版本 | 建置結果可能隨 backend 版本變動 |
| `websockets` | 實驗性 voice session WebSocket | 未宣告於 `pyproject.toml` | 由文件手動安裝，版本漂移 |
| `sounddevice` | 實驗性 voice 麥克風輸入 | 未宣告於 `pyproject.toml` | binary wheel 與 Python/macOS 版本耦合 |
| `numpy` | 實驗性 voice 音訊處理 | 未宣告於 `pyproject.toml` | binary wheel 與 Python 版本耦合 |

`pyproject.toml` 目前沒有 `[project.optional-dependencies]`，也沒有 pytest 相關測試相依宣告。

---

## 3. 打包與安裝現況

| 項目 | 現況 | 影響 |
|------|------|------|
| 套件版本 | `desktop-harness = 0.4.2` | 升級計畫應以 minor/patch 前進，避免一次跨多個破坏性變更 |
| CLI entry point | `desktop-harness = "desktop_harness.run:main"` | 升级後必須驗證進入點仍可用 |
| wheel 打包 | hatchling，`packages = ["src/desktop_harness"]` | 需驗證 `desktop_harness/data/SKILL.md` 仍被包含 |
| SKILL.md 打包 | `force-include` 根 `SKILL.md` 到 `desktop_harness/data/SKILL.md` | 文件雙份真相，有漂移風險 |
| `install.sh` | `pip install -q -U pip` 後安裝三個未鎖版本 pyobjc，再 `pip install -e . --no-deps` | 安裝結果不可重現；依赖解析依賴當下 PyPI 狀態 |
| launcher | `desktop-harness` 使用 `$DIR/.venv/bin/python`，否則退回 `python3` | venv 損壞或 Python 版本不符時失敗訊息不友善 |
| license metadata | 有 `LICENSE`，但 `pyproject.toml` 未宣告 license 中繼資料 | wheel metadata 不完整 |

---

## 4. 執行環境

| 層級 | 現況 |
|------|------|
| 平台 | macOS，建議 Sequoia+ |
| 主要界面 | CLI + heredoc Python script |
| 核心能力 | Accessibility tree、CGEvent 真實鍵鼠、視窗截圖 |
| 常駐元件 | 選用 warm daemon；Unix socket 0600 + token 0600 |
| 檔案足跡 | `~/.desktop-harness/audit.jsonl`、`~/.desktop-harness/daemon.token`、`~/Library/Caches/desktop-harness/daemon.sock`、`~/Library/Caches/desktop-harness/daemon.pid` |
| 系統權限 | Accessibility、Screen Recording；Screen Recording 授權後通常需重啟 host app |
| 可選語音 | `scripts/voice_session.py` 連接 `wss://api.x.ai/v1/realtime`，需要 `XAI_API_KEY`；不得在文件或測試中放入真實金鑰 |
| 自動更新 | 無靜默自動更新；`check-update` 為選用 |

---

## 5. 現有測試與驗證工具

| 工具 | 現況 | 升級風險 |
|------|------|----------|
| `desktop-harness --doctor` | 檢查 pyobjc import、Accessibility、Screen Recording、前景 app AX、視窗列表 | 適合作為升級後第一道關卡 |
| `desktop-harness selftest` | 非破壞自測，但會開 TextEdit、移動滑鼠、啟動 daemon | 可作為實機回歸，但需專人看結果 |
| `desktop-harness demo` | 可見煙霧測試，會真實操作 GUI | 需先確認目標視窗存在，否則不應作為自動 gate |
| pytest | 未在 `pyproject.toml` 設定 | 缺自動化測試地基 |
| CI workflow | 本快照未提供；且本任務禁止修改 workflows | 自動化 CI 不在本計畫範圍 |

---

## 6. 實作前應補抓的環境事實

以下指令應在實際升級前於目標 Mac 與目標 Python venv 執行，並將結果寫入 PR 紀錄，不要寫入 repo：

```bash
python3 --version
python3 -m pip --version
python3 -m pip check
python3 -m pip show pyobjc-framework-Quartz
python3 -m pip show pyobjc-framework-Cocoa
python3 -m pip show pyobjc-framework-ApplicationServices
python3 -m pip show hatchling
sw_vers
uname -m
desktop-harness --version
desktop-harness --doctor
desktop-harness daemon status
```

若同時要評估實驗性 voice 環境：

```bash
python3 -m pip show websockets
python3 -m pip show sounddevice
python3 -m pip show numpy
```

voice 金鑰驗證只應確認環境變數是否存在，不可印出值；測試值一律使用 `FAKE_VALUE_FOR_TEST`。
