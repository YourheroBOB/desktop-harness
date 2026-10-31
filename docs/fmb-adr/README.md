# desktop-harness 架構決策紀錄（ADR）索引

本目錄收錄 desktop-harness 現有架構中**隱含的重要設計決策**，以 ADR（Architecture Decision Record）形式整理：每一篇包含**背景、決策、取捨、後果**。這些決策大多原本散落在 `DESIGN.md`、`SKILL.md`、`SECURITY.md`、postmortem 與程式碼註記中；此處將其顯性化，方便新進開發者理解「為什麼是這樣」而不是只看到「現在是這樣」。

## ADR 清單

| 編號 | 標題 | 狀態 |
|------|------|------|
| [ADR-0001](./ADR-0001-ax-first-perception.md) | AX 優先的分層感知（Shell → AX → 視窗截圖 → 視覺） | 接受中 |
| [ADR-0002](./ADR-0002-cli-not-mcp.md) | 以 CLI + Skill 為產品形態，而非 MCP server | 接受中 |
| [ADR-0003](./ADR-0003-arbitrary-exec-surface.md) | 以「任意 Python script」作為 agent 介面（exec 模型） | 接受中（需理解爆炸半徑） |
| [ADR-0004](./ADR-0004-warm-daemon-token-auth.md) | 常駐 warm daemon + Unix socket + token 認證 | 接受中 |
| [ADR-0005](./ADR-0005-real-hid-single-cursor.md) | 真實系統游標 + 單一游標 presence UI（不畫第二個箭頭） | 接受中 |
| [ADR-0006](./ADR-0006-appkit-main-thread.md) | AppKit 嚴格 main-thread 約束：以分片 wait 取代背景執行緒 | 接受中 |
| [ADR-0007](./ADR-0007-media-look-once.md) | 媒體控制「先讀狀態、只做一次動作」（look-once, act-once） | 接受中（源自實際事故） |
| [ADR-0008](./ADR-0008-sensitive-app-gates.md) | 敏感應用程式的 runtime 阻擋 + 審計日誌 | 接受中（擋截圖同於擋點擊） |
| [ADR-0009](./ADR-0009-verify-after-mutation.md) | 變更畫面後必須 `verify()`：回傳路徑 ≠ 畫面成功 | 接受中 |
| [ONBOARDING.md](./ONBOARDING.md) | 新進開發者上手指南（模組地圖、資料流、修改路徑、陷阱） | — |

## 讀法建議

- 想知道「為什麼不用 screenshot→vision 迴圈」→ 從 ADR-0001 開始。
- 想知道「為什麼不是 MCP」→ ADR-0002 + ADR-0003。
- 要動 daemon、安全、或 presence 相關程式 → ADR-0004、0005、0006、0008 必讀。
- 要動 `helpers.py` 的動作類 API → ADR-0007、0009 必讀（都是花過事故學費的決策）。
