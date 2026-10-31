# ADR-0002：CLI + Skill，而非 MCP server

**狀態：** 接受中（MCP wrapper 列為 roadmap「之後可選」）  
**相關模組：** `run.py`（CLI 進入點）、`SKILL.md` / `data/SKILL.md`

## 背景

agent 生態有兩種常見的工具接法：(a) MCP 之類的 RPC tool server，(b) 直接跑 shell 指令。desktop-harness 的主要用戶（Grok Build 等 coding agent）**本來就有 shell 能力**；為了Mac 控制再架一層 RPC server，會增加安裝、生命週期管理與協定維護的成本，卻沒有增加能力。

## 決策

產品形態是：

- **CLI** `desktop-harness`，以 stdin heredoc 接收 Python script 並執行（見 ADR-0003）。
- **Skill 檔**（`SKILL.md`）教 agent「何時、如何」呼叫這個 CLI，並由 `desktop-harness skill` 輸出、安裝到 `~/.grok/skills/`。
- **可選 warm daemon** 提速（見 ADR-0004），但 CLI 本身隨時可獨立運作（`DH_NO_DAEMON=1` 強制 in-process）。
- MCP **不**是核心；未來若要做，也只是包同一層 API 的薄 wrapper。

## 取捨

- 放棄了 tool-shaped RPC 的型別安全與工具清單自動發現；換來**最低摩擦**的整合——任何能跑 shell 的 agent（Claude Code、Codex CLI、純腳本）都能立刻使用。
- 放棄了「工具粒度」的控管：MCP 可以逐一暴露/限制工具；CLI 的 exec 模型一旦能跑就全都能跑（風險討論見 ADR-0003、ADR-0008）。
- Skill 是「教學文件 + 觸發條件」，不是程式碼；這意味著行為規範（如媒體規則、consent）靠的是 skill 文字，執行面只靠 `safety.py` 的 runtime gate。

## 後果

- 整合面極薄：安裝 = venv + PATH shim + 一份 SKILL.md。
- Skill 檔有**兩份**（repo 根目錄 `SKILL.md` 與打包用的 `src/desktop_harness/data/SKILL.md`），wheel 打包靠 `pyproject.toml` 的 force-include——兩份內容需人工保持同步（歷史上曾因此出過 `skill` 指令在非 checkout 環境壞掉的問題，見 `docs/PRE-RELEASE-REVIEW.md` #4）。
- 若日後生態全面轉向 MCP，此決策可被 ADR 推翻，但核心函式庫（`helpers.py` 等）不需重寫。
