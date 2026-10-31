# 敏感欄位政策：日誌中禁止出現的內容

> 這是整份可觀測性設計的**紅線文件**。任何事件、指標、報告、告警、錯誤訊息都受本章約束。
> 違反 = ALRT-06（P1）：停止寫入、保全現場、修復並補測試後才恢復。

## 1. 分級

| 級別 | 規則 |
|------|------|
| **FORBIDDEN** | 永不入任何觀測輸出。沒有開關、沒有 hash 例外（hash 只適用於 restricted）。 |
| **RESTRICTED** | 預設不記原文；記 `_hash`（SHA-256 hex 前 12 碼）/ `_len` / 計數，或由明確 env 開關決定。 |
| **INTERNAL** | 可記（本機檔案）。仍須經過 sanitizer，且檔案權限 0600。 |

## 2. FORBIDDEN 清單（永不記錄）

| # | 類別 | 具體項目 |
|---|------|----------|
| F1 | 使用者輸入內容 | `type_text` / `set_field` / paste 的文字、任何按鍵序列內容、語音轉寫稿 |
| F2 | 剪貼簿 | `get_clipboard` / `set_clipboard` 的內容與長度以外的任何推導 |
| F3 | AX 屬性值 | 節點 `value`、`AXSelectedText`、任何 AXValue 型別內容（**密碼欄位值就住在這裡**） |
| F4 | 螢幕內容 | 截圖影像、OCR／vision 輸出、`screencapture` 位元組流 |
| F5 | 憑證與機密 | daemon token 檔內容、任何 `*_API_KEY`／token／password 類環境變數的值、auth 檔內容 |
| F6 | 身分與個資 | 登入使用者名稱、絕對 home 路徑（`/Users/<name>` 型態）、郵件地址、案件當事人資料、LINE 訊息內文（依公司政策一律不碰） |
| F7 | 可能帶密的形式 | 完整 URL（可能含 token/query）、搜尋關鍵字原文 |
| F8 | 未處理的例外原文 | 未正規化的 traceback／message（可能夾帶上述任何一項） |

> 關於 F5：本文件只寫「環境變數**名稱**」作為掃描關鍵字的來源類別，不寫任何值；範例一律用 `FAKE_VALUE_FOR_TEST`。

## 3. RESTRICTED 清單（預設降級）

| 項目 | 處理方式 |
|------|----------|
| `find` / `click_text` 的查詢字串、目標標籤 | `query_hash` + `query_len` |
| 視窗標題 | 預設不記；`DH_LOG_WINDOW_TITLES=1` 才記，且視為 internal |
| 截圖路徑 | 只記 `path_basename`（`$TMPDIR` 可能含 uid） |
| CLI argv / stdin 腳本 | 只記 `argv_count` / `stdin_bytes` |
| 螢幕座標 | internal（低敏感，保留供重現） |
| app 顯示名稱 / bundle id | internal（審計需要；敏感 app 的**阻擋紀錄**尤其要留） |
| 自由訊息 | `sanitized_message`：數字→`<n>`、路徑→`<path>`、引號內字串→`<str>` 後才可記 |

## 4. Redaction 管線（落地時的驗收條件）

```
event fields ──► allowlist 驗證 ──► restricted 降級（hash/len）──► sanitizer ──► 寫入
                     │未知欄位 → 測試環境 raise
                     │FORBIDDEN 類型值 → 丟棄 + dh_forbidden_field_hits_total{field}++
```

**靜態掃描樣式**（維護於掃描器設定，不把完整樣式表寫死在文件裡；類別包含）：

- 已知金鑰前綴（各雲端／VCS／聊天工具的 token 前綴家族）
- `Bearer `、`Authorization:`、`password=`、`passwd`、`secret`
- 絕對 home 路徑型態、`/Users/`、`/home/`
- 高熵長字串（長度 ≥ 32 且熵超標）→ 送人工審核佇列
- 公司政策關鍵字（當事人、案件號等）→ 一律 ALRT-06

掃描時機：寫入前（redaction 層）、每次 `report`（對 `events.jsonl` 樣本）、CI（見未完成事項）。

## 5. 好／壞日誌範例

**壞（違反 F1／F3／F6）：**

```json
{"event":"type_text","fields":{"app":"TextEdit","text":"FAKE_VALUE_FOR_TEST","user":"/Users/FAKE_VALUE_FOR_TEST"}}
{"event":"set_field","fields":{"field_label":"Password","value":"FAKE_VALUE_FOR_TEST"}}
{"event":"ax_snapshot","fields":{"nodes":[{"title":"Email","value":"FAKE_VALUE_FOR_TEST"}]}}
{"event":"error","fields":{"message":"no window for app='/Users/FAKE_VALUE_FOR_TEST/Documents/私密文件.txt'"}}
```

**好（同一意圖，降級後）：**

```json
{"event":"type_text","fields":{"app":"TextEdit","char_count":17,"duration_ms":136,"result":"ok"}}
{"event":"set_field","fields":{"app":"System Settings","field_label_hash":"a1b2c3d4e5f6","field_label_len":8,"value_len":12,"result":"ok"}}
{"event":"ax_snapshot","fields":{"app":"Safari","interactive_only":true,"nodes_count":42,"truncated":false,"duration_ms":88}}
{"event":"error","fields":{"error_class":"window_not_found","module":"capture","sanitized_message":"no on-screen window for app='<str>'"}}
```

## 6. 靜默失敗條款

觀測寫入（audit/events/metrics）失敗時：

1. 向 stderr 輸出**一行**摘要（不含敏感內容，例如 `[observability] write failed target=events class=io_error`）。
2. 盡最大努力發一筆 `audit_write_failed` 事件（避免遞歸：此事件只用內建常數組裝，不再呼叫可能失敗的 redaction）。
3. **不允許** `except: pass`——現有 `safety.audit()` 正是此反模式（見 `CURRENT-STATE.md` G2）。

## 7. 保留

| 檔 | 保留 |
|----|------|
| `events.jsonl`（含輪替副本） | 最近 3 份／15MB |
| `metrics.jsonl` | 彙總後 30 天 |
| `audit.jsonl` | 依 BOB 決策（預設建議同 events，見摘要決策點） |

到期刪除必須是**檔案級刪除**，不做「部分欄位覆寫」那種自欺手法。
