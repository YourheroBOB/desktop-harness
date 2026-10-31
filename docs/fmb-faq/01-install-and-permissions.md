# 01 · 安裝與權限（FAQ A1–A8）

## A1 · `desktop-harness: command not found`

- **問題：** `install.sh` 跑完後，shell 找不到 `desktop-harness` 指令。
- **原因：** 安裝把 shim 放在 `~/.local/bin`，但該路徑不在 `PATH`。
- **解法：** `export PATH="$HOME/.local/bin:$PATH"`，並寫進 shell rc 檔。安裝結尾訊息有提示此事。
- **相關檔案：** `install.sh`、`install.md`、`README.md`。

## A2 · `--doctor` 顯示 Accessibility FAIL

- **問題：** `desktop-harness --doctor` 的 Accessibility 檢查不過。
- **原因：** 執行 CLI 的 **host 應用**（Terminal、Ghostty、iTerm 或 agent host）沒有被授予 Accessibility 權限。AX 讀取與滑鼠鍵盤注入（`CGEvent`）都需要它。
- **解法：** 開啟「系統設定 → 隱私權與安全性 → 輔助使用」，勾選**實際執行指令的那個 host**（不是 desktop-harness 本身），再重跑 `--doctor`：
  ```bash
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
  ```
- **相關檔案：** `src/desktop_harness/admin.py`（`AXIsProcessTrusted` 檢查）、`install.md`。

## A3 · `--doctor` 顯示 Screen Recording FAIL / 截圖空白

- **問題：** Screen Recording 檢查 FAIL，或截出來的 PNG 是空的。
- **原因：** host 未取得 Screen Recording 權限；doctor 是用「實拍一張並檢查檔案大小 > 1000 bytes」來驗證，權限缺失時會拍到空影像。
- **解法：** 授權 Screen Recording 給 host app。注意核心的 AX 控制不需要此權限——只有截圖 fallback 需要。
- **相關檔案：** `src/desktop_harness/admin.py`、`src/desktop_harness/capture.py`。

## A4 · `--doctor` 顯示 pyobjc 匯入失敗

- **問題：** `pyobjc frameworks (Quartz, AppKit, ApplicationServices)` 檢查 FAIL。
- **原因：** 跑到 doctor 的 Python 不是專案 venv（沒裝 pyobjc），或 venv 尚未建立。doctor 在這項失敗時會直接結束，因為後續檢查全依賴它。
- **解法：** 確認用的是 `install.sh` 建的 `.venv`（`~/.local/bin/desktop-harness` shim 會指向它）；手動安裝路徑見 `install.md`：
  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices
  pip install -e . --no-deps
  ```
- **相關檔案：** `install.sh`、`install.md`、`pyproject.toml`。

## A5 · Screen Recording 已授權，截圖還是失敗

- **問題：** 設定頁明明已勾選，`screenshot()` 或 doctor 的 capture 檢查仍失敗。
- **原因：** macOS 的 Screen Recording 權限**授予後必須完整結束並重啟 host app** 才生效——只關視窗不夠。
- **解法：** 完全退出 Terminal／Ghostty／agent host 後重新啟動，再跑 `--doctor`。doctor 的輸出與 `install.md` 都有提醒這點。
- **相關檔案：** `install.md`、`install.sh`（結尾提示）、`src/desktop_harness/admin.py`。

## A6 · `desktop-harness skill` 在 pip / wheel 安裝下失敗（歷史問題）

- **問題：** 在非原始碼 checkout 的環境執行 `desktop-harness skill` 丟 `FileNotFoundError`。
- **原因：** 歷史版本 `run.py` 用相對路徑回推 repo 根目錄讀 `SKILL.md`，wheel 安裝時該路徑不存在（pre-release review #4）。
- **解法：** v0.4.2 已透過 `pyproject.toml` 的 `force-include` 把 `SKILL.md` 打包成 `desktop_harness/data/SKILL.md`，新版 wheel 不再有此問題。若仍遇到，升級到 ≥ v0.4.2，或改用 `pip install -e .` 的 editable 安裝。
- **相關檔案：** `pyproject.toml`、`src/desktop_harness/data/SKILL.md`、`docs/PRE-RELEASE-REVIEW.md`（#4）、`docs/fmb-adr/ADR-0002-cli-not-mcp.md`。

## A7 · 第一次 CLI 呼叫特別慢

- **問題：** 每次冷啟動的 `desktop-harness <<'PY' … PY` 都要等一段時間。
- **原因：** in-process 路徑每次都要啟動 Python 並匯入 pyobjc（冷啟動成本）。
- **解法：** 多步任務先啟動 warm daemon，第二步起自動路由到常駐行程，明顯變快：
  ```bash
  desktop-harness daemon start --bg
  desktop-harness daemon status
  ```
- **相關檔案：** `src/desktop_harness/daemon.py`、`src/desktop_harness/run.py`、`docs/fmb-adr/ADR-0004-warm-daemon-token-auth.md`。

## A8 · 可以在 Linux / 舊版 macOS 上跑嗎

- **問題：** 想在非 macOS 環境使用 desktop-harness。
- **原因：** 全部能力都建立在 macOS 專有 API 上：AX（ApplicationServices）、CGEvent／CGWarp（Quartz）、NSWorkspace／AppKit（Cocoa）。
- **解法：** 不行也不規劃支援；macOS Sequoia+ 為建議環境、Python ≥ 3.10。Linux 上請改用其他工具。
- **相關檔案：** `pyproject.toml`（`requires-python`、pyobjc 相依）、`install.md`。
