# ADR-0011：核心零網路依賴；語音與更新檢查維持選用、實驗性、需明確金鑰

- **狀態：** 接受中
- **日期：** 2026-08
- **相關：** [ADR-0002](./ADR-0002-cli-not-mcp.md)、`VOICE.md`、`README.md`、`docs/fmb/ROADMAP-ZH-TW.md`

## 背景

desktop-harness 是一個能移動真實滑鼠、讀取螢幕內容的本機工具，天然有兩個「連網」誘因：

1. **語音控制**（`VOICE.md`）：Grok Voice Think Fast 2.0 是 WebSocket 服務，需要 `XAI_API_KEY`，且 Grok Build 登入不等於擁有 API 額度。
2. **版本更新**：希望使用者永遠用最新版。

但一個預設聯網、又能動你滑鼠的工具，信任邊界與攻擊面都會大幅擴大：它隨時可能被中間人、被依賴套件、或被自己的更新機制改寫行為。`docs/fmb/ROADMAP-ZH-TW.md` 因此把「核心 CLI 維持零網路依賴」與「禁止靜默自動更新」列為明確非目標（另見 [ADR-0015](./ADR-0015-explicit-non-goals.md)）。

## 決策

1. **核心控制路徑 100% 本機**：`pyproject.toml` 的 dependencies 只有三個 pyobjc 框架；AX 讀取、滑鼠鍵盤注入、截圖、daemon 都不依賴任何網路服務。
2. **語音是選用實驗功能**：以 `scripts/voice_session.py` + `src/desktop_harness/voice_tools.py` 形式存在，需要使用者自備 `XAI_API_KEY`（環境變數或 Keychain，永不寫進文件）；無 key 時明確退出；`--dry-run` 只印工具呼叫計畫，不碰真實 GUI。
3. **無靜默自動更新**：`desktop-harness check-update` 只被動比對 GitHub 版本號；更新一律由使用者手動 `git pull` + `install.sh` 觸發。理由如 README 所寫：會動滑鼠的程式碼，何時改變必須由使用者自己決定。

## 取捨

- **優點**：核心可離線審查與執行；攻擊面小；依賴樹短；語音實驗的 API 金鑰、計費、協定變動不會波及主產品。
- **缺點**：語音功能門檻高（要自備 key 與額度）；核心不會自動修 bug，版本可能落後；「實驗性」功能容易與核心文件混淆，需要持續的文件紀律。

## 後果

- 新增任何需要連網的功能，必須走 optional／實驗通道（獨立腳本或 extras）並在文件明講；不得把 websockets 等依賴放進核心 dependencies（方向同 `docs/fmb-review` PKG-3）。
- 驗證語音功能時不得連線正式服務：用 mock WebSocket 或 `--dry-run`；假憑證一律使用 `FAKE_VALUE_FOR_TEST`。
- `VOICE.md`、`docs/fmb-api/voice-tools.md` 必須持續標示語音的實驗狀態與金鑰需求，避免使用者誤以為 Grok Build 登入就包含語音能力。
