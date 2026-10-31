# ADR-0009：變更畫面後必須 `verify()`

**狀態：** 接受中（skill 中的 mandatory 規則）  
**相關模組：** `helpers.py`（`verify(note, app?)`）、`capture.py`

## 背景

`click_text` / `set_field` 沒丟例外，只代表 **AX 呼叫成功**——不代表畫面變成了預期樣子。按鈕可能 disabled、彈窗可能蓋住、動作可能無效果。agent 若把「沒例外」當「成功」回報使用者，就是在沒看畫面的情況下斷言畫面狀態。

## 決策

任何**意在改變畫面**的動作之後，必須：

1. 呼叫 `verify("預期發生什麼")`；
2. **讀取它回傳的截圖路徑**（agent 用視覺讀圖）；
3. 之後才能向使用者宣稱該步驟成功。

純探索呼叫（`labels`、`ax_snapshot`）不改變任何東西，可豁免。成本是一次額外呼叫——skill 明言這是「probably clicked something」與「actually knowing」的差別。

## 取捨

- 每次變異多一次截圖（50–150 ms + 一張 PNG 的 context 成本）；換來把「斷言成功」建立在**像素證據**而非 API 回傳值上。
- 這與 ADR-0001 的「不要 vision loop」**不矛盾**：verify 是「一次、收尾」的證據檢查，不是每步循環的視覺依賴。observe loop（`docs/OBSERVE-LOOP.md`）則是這個原則在「迭代視覺成果」場景的加強版（多影格、密集捕捉）。
- 對不可截圖的場景（敏感 app gate 擋下）verify 會失敗——那是正確行為：擋截圖本身就是安全決策。

## 後果

- 「回傳成功 ≠ 畫面成功」成為 agent 行為規範的核心句，也解釋了為什麼 harness 把「給你當下像素 + 狀態」定位為自己的職責，而判斷留給 agent。
- 新增任何會改變畫面的 helper 時，考慮是否內建 verify 或在文件中標注需要外部 verify。
- 截圖路徑已改為每次唯一（`capture-{pid}-{ts}.png`），並發 agent 步驟不會互相覆蓋（review #17 的修正）——這是 verify 可靠的前提。
