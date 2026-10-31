# 個人資料類別與流向盤點（資料地圖）

> 界定原則：desktop-harness 本身不針對特定當事人蒐集資料，但任何透過它讀取／截取／輸入／外傳的內容，都可能落入個資法「個人資料」定義（姓名、出生年月日、國民身分證統一編號、特徵、指紋、婚姻、家庭、教育、職業、病歷、醫療、基因、性生活、健康檢查、犯罪前科、聯絡方式、財務情況、社會活動及其他得以直接或間接識別該個人之資料）。以下依「程式會碰到的資料面」盤點。

## 1. 資料類別 × 產出位置總表

| # | 資料面 | 內容性質（可能含個資） | 落地位置 | 程式碼/文件依據 | 是否離開本機 |
|---|--------|------------------------|----------|------------------|----------------|
| D1 | 視窗／全螢幕截圖 PNG | 螢幕上一切可見內容：文件、訊息、姓名、帳號、財務、就醫紀錄等 | `$TMPDIR/desktop-harness/capture-<pid>-<ns>.png`（永不清理）；`dh-doctor.png`（固定路徑）；`/tmp/dh-observe/*.png`（observe script） | `capture.py`、`admin.py`、`scripts/observe-demo.sh`；PERC-3/PERC-4 | agent 若讀圖並回傳 → 是 |
| D2 | AX 樹內容（label／value／title） | 任何 app UI 的結構化文字：**含輸入欄位的 `value`（已打字內容）**、視窗標題（常含文件名／收件人名）、訊息內文 | 僅存在 process 記憶體，隨 stdout 回傳 agent | `ax.py`、DESIGN.md（快照欄位含 `value`）、ADR-0001 | 是——stdout 直接進 agent／LLM context |
| D3 | 視窗清單／app 清單 | app 名稱、視窗標題（→ 檔名、網頁標題、訊息對象） | stdout 回傳 | `windows.py` | 是（同上） |
| D4 | agent 腳本 stdout | agent `print()` 任何它讀到的內容（labels、截圖路徑、欄位值） | agent 端（LLM 服務商，多為境外） | `run.py` exec 模型、ADR-0003 | **是——跨境** |
| D5 | audit log | 事件、時間戳、app 名稱、window_id、截圖路徑、（依呼叫者）click 目標文字 | `~/.desktop-harness/audit.jsonl`（無上限成長） | `safety.py`；TR-4/OBS-2 | 否（本機） |
| D6 | 鍵盤輸入內容 | `type_text`／`set_field` 的值（可能為密碼以外的敏感內容：訊息草稿、個資表格） | 直接進目標 app；**刻意不寫入 audit** | `safety.py` 註解、ADR-0008 | 視目標 app 而定 |
| D7 | daemon token／socket／pid 檔 | 認證憑證與行程 metadata | `~/.desktop-harness/daemon.token`（0600）、`~/Library/Caches/desktop-harness/` | `daemon.py`、ADR-0004 | 否 |
| D8 | voice 音訊＋文字稿 | 使用者語音、對話內容（**語音即個人資料**；可能提及當事人） | 即時送往 `wss://api.x.ai/v1/realtime`（境外）；transcript 列印至 stdout | `scripts/voice_session.py`、VOICE.md | **是——跨境** |
| D9 | voice API key | 認證憑證 | 環境變數或 macOS Keychain | `voice_session.py`、`voice_hotkey_readme.md` | 僅傳給 xAI（認證用） |

## 2. 流向圖（重點：本機 vs 境外）

```
                    ┌──────────── 本機（個資落地） ────────────┐
 螢幕/AX 內容 ──► capture PNG（$TMPDIR，永久）                │
             ──► audit.jsonl（~/.desktop-harness，永久）      │
             ──► daemon token（0600）                         │
                    └──────────────────────────────────────────┘
                    ┌──────────── 境外（跨境傳輸） ─────────────┐
 stdout（AX 值、視窗標題、labels、截圖讀取結果）─► agent host ─►
   Grok Build / 其他 LLM 服務商（模型推論，內容進其基礎設施）   │
 voice 音訊/文字稿 ─► api.x.ai Realtime WS（美國）             │
                    └──────────────────────────────────────────┘
```

**關鍵事實：**
1. **零網路是對「harness 核心」的宣稱**（`docs/fmb/ARCHITECTURE.md` §4.4），但 agent 使用模式必然把 AX 內容／截圖讀取結果放進 LLM context——個資是否跨境取決於 **agent host**，而本 repo 的文件未對此做任何告知或最小化設計。
2. **截圖無敏感遮罩**：`safety.py` 只擋「密碼管理器類 app」的截圖（ADR-0008）；其他任何 app（mail、訊息、文件、網銀頁面）的截圖內容不受任何處理即落檔、即可能被 agent 讀取外傳。
3. **AX `value` 欄位是隱性大戶**：文件與 ADR 都說快照含 `value`——這代表使用者先前輸入的欄位內容（可能為他人個資）會被 `labels()`／`ax_snapshot()` 直接讀出。
4. `screenshot`／`type_text` 的敏感阻擋**只覆蓋 helper 路徑**，任意 exec 可繞過（ADR-0003 既定界限）——合規上必須把「繞過可能性」計入風險。

## 3. 特種個人資料（個資法 §6 敏感類別）曝露面

截圖與 AX 讀取**無內容過濾**，若螢幕上出現病歷／醫療、財務（網銀、記帳）、犯罪前科（判決文件——律師情境常見）等特種個資，會原樣進入 D1/D2/D4 流向，無任何降敏機制。對以本工具執行業務的情境，這是最高風險項之一（對應 pdpa-gap-analysis.md COMP-1／COMP-9）。

## 4. 盤點結論

- 個資「觸點」集中在：**截圖（D1）、AX 值讀取（D2/D3）、stdout 外傳（D4）、voice（D8）**。
- 本機落地檔案皆**無保存期限、無刪除機制**（見 retention-and-deletion.md）。
- 境外流向（D4/D8）**無告知、無最小化、無當事人同意設計**（見 pdpa-gap-analysis.md）。
- 認證憑證（D7/D9）管理得當（0600／env／Keychain），無寫入 repo 風險（`.gitignore` 排除 `.venv` 等，review #23 確認無 secret 入庫）。
