# 01 · 盤點：語言版本、相依套件與執行環境

> 來源：`pyproject.toml`、`install.sh`、`install.md`、`desktop-harness`（dev launcher）、`scripts/voice_session.py`、`VOICE.md`、`SECURITY.md`。僅盤點，未做任何變更。

## 1. 語言與執行環境

| 項目 | 現況 | 備註 |
|------|------|------|
| Python 版本需求 | `requires-python = ">=3.10"`（未設上限） | 未鎖上界；未來 Python 3.14+ 若有破壞性變更，`pip install` 仍會宣稱相容 |
| 實際執行 Python | `install.sh` 與 dev launcher 都用系統 `python3` | 未指定次要版本；macOS 內附 python3 版本隨系統漂移 |
| 作業系統 | macOS（README 稱 Sequoia+ 建議，早期版本「可能可用」） | pyobjc bridge 與 macOS SDK 綁定，是升級的主要風險來源 |
| 套件管理 | `python3 -m venv .venv` + `pip install -e . --no-deps` | 無 lock 檔（無 requirements.txt lock、無 pip-tools、無 uv.lock） |
| 建置系統 | `hatchling`（未鎖版本） | `pip install -e .` 時由 pip 現場解析 |

## 2. 執行期相依（pyproject.toml `dependencies`）

| 套件 | 宣告方式 | 風險註記 |
|------|----------|----------|
| `pyobjc-framework-Quartz` | **無版本約束**（完全浮動） | 提供 CGEvent / CGWindowList / 螢幕座標；`input.py`、`capture.py`、`windows.py` 直接依賴其 API |
| `pyobjc-framework-Cocoa` | **無版本約束** | 提供 AppKit（NSWorkspace、NSRunningApplication、NSBitmapImageRep、presence overlay）；使用量大 |
| `pyobjc-framework-ApplicationServices` | **無版本約束** | 提供 `AXIsProcessTrusted` 與 AX API；`ax.py` 的核心 |

**三個相依都未 pin**，意即：

- 今天全新 `./install.sh` 與一個月後的 `./install.sh` 可能裝到**不同大版本**的 pyobjc。
- pyobjc 大版本升級（例如伴隨新 macOS SDK 的版本）歷史上曾出現 enum 常數搬移、橋接型別行為改變等破壞性變更；本 repo 的 `ax.py` 曾因型別常數問題被 review 點名（PRE-RELEASE-REVIEW #14：magic int `1`/`2` 應改用 `kAXValueCGPointType` 等常數）。
- `pip install -e . --no-deps` 只是不安裝宣告相依，pyobjc 由 install.sh 前一段裸裝，同樣未鎖版。

## 3. 未宣告／可選相依

| 套件 | 使用處 | 現況 |
|------|--------|------|
| `websockets` | `scripts/voice_session.py`（Realtime WS） | 未列於 pyproject；執行時 `import websockets` 失敗才提示手動 `pip install` |
| `sounddevice` | 語音麥克風串流（VOICE.md 規劃，程式未接線） | 僅文件提及 |
| `numpy` | 語音 PCM 處理（規劃中） | 僅文件提及 |
| `rumps` | menubar app（未來選項） | 僅文件提及 |
| 系統外部指令 | `open`、`osascript`、`screencapture`（selftest / observe-demo） | 屬 macOS 內建，隨系統升級漂移，非 pip 可控 |

**問題：** voice 是 repo 的一部分但相依完全未宣告，且無 optional-dependencies 群組（`[project.optional-dependencies]`），使用者無法以 `pip install .[voice]` 一次裝齊。

## 4. 開發／測試環境

| 項目 | 現況 |
|------|------|
| 測試框架 | **無**（無 pytest、無 tests/、無 CI workflow） |
| Lint / format 工具 | 無 |
| `pyproject.toml` dev 群組 | 無 `[project.optional-dependencies]`、無 hatch env |
| 版本一致性 | `__init__.py` 與 `pyproject.toml` 皆為 0.4.2 ✅（PRE-RELEASE-REVIEW #3 的版本漂移問題已修） |

## 5. 執行環境的其他元件

| 元件 | 說明 |
|------|------|
| Warm daemon | Unix socket（0600）+ token 檔（0600）於 `~/.desktop-harness/`／`~/Library/Caches/desktop-harness/`，與 Python 版本無直接耦合，但 daemon 內 `exec()` 的 namespace 隨程式碼演進 |
| Audit log | `~/.desktop-harness/audit.jsonl`，無 rotation（review #18 已點名） |
| Grok skill | `desktop-harness skill` 輸出 SKILL.md，安裝到 `~/.grok/skills/` |
| `~/.local/bin/desktop-harness` shim | 硬連到 repo 內 `.venv`，repo 搬移或 venv 重建後需重跑 install.sh |

## 6. 環境資訊缺口（本文件無法取得）

以下資訊在 repo 靜態內容中不可得，執行升級前需在目標機上確認：

- 目標機實際 macOS 版本（決定相容的 pyobjc 上界）
- 目標機 `python3 --version`（venv 來源）
- `.venv` 內目前實際安裝的 pyobjc 版本（`pip freeze`）
