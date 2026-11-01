# ADR-0012：審計日誌記錄「行動中繼資料」，不記錄「輸入／訊息內容」

- **狀態：** 接受中
- **日期：** 2026-08
- **相關：** [ADR-0008](./ADR-0008-sensitive-app-gates.md)、[ADR-0010](./ADR-0010-consent-at-agent-policy-layer.md)、`SECURITY.md`

## 背景

審計日誌（`~/.desktop-harness/audit.jsonl`）要能回答事後問題：「agent 剛才對這台 Mac 做了什麼？」但同一支工具也會碰到機密內容——打進密碼欄位的字元、剪貼簿上的 Token、訊息內文、截圖裡的敏感畫面。

如果把內容也記進 audit log，等於為了問責而製造第二個洩漏點：log 檔比螢幕更容易被分享（貼 issue、傳訊息、進 CI artifact）。`docs/fmb/ROADMAP.md` 對剪貼簿 helper 的設計要求即是「audit 只記長度不記內容」；架構文件亦載明 audit 記「時間戳記與參數（不記錄輸入內容字串）」。

## 決策

1. audit log 只記錄**行動中繼資料**：動作類型、時間戳、目標 app／元素識別、結果成功與否；例如 `activate`、`click_text`、`screenshot`、`ensure_media_playing`。
2. **不記錄內容本體**：`type_text` 的字串、剪貼簿文字、訊息內文、截圖影像一律不進 log（截圖只記檔案路徑）。
3. 未來的剪貼簿等 helper 沿用同一規則：最多記長度或雜湊，不記值。

## 取捨

- **優點**：log 可安心分享給除錯、審計、issue；問責與隱私不再互相拉扯；與「截圖敏感前景 = 洩漏」的閘門精神（ADR-0008）一致。
- **缺點**：事後無法從 log 重現「到底打了什麼」，只能靠當事人或終端機 scrollback；長度指紋在極短字串上辨識力有限。

## 後果

- 新增 helper 時，「audit 記什麼」是設計審查項目之一；寧可少記也不可記內容。
- 已知缺口（尚未成文決策，需 BOB 確認）：audit 目前無輪替與保留政策、`safety.audit()` 靜默吞掉例外（見 `docs/fmb-perf` TR-4／OBS-2 與 ROADMAP 第 7 項）。補輪替時必須維持「不記內容」的性質不變。
