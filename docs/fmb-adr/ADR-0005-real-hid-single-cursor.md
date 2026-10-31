# ADR-0005：真實系統游標 + 單一游標 presence UI

**狀態：** 接受中（「不畫第二個箭頭」是踩過雷後的明文規則）  
**相關模組：** `input.py`（CGEvent/CGWarp）、`presence.py`（halo/pill）

## 背景

agent 控制桌面時，人類需要**看得出**「現在是 agent 在動，手別伸進去」。兩個做法：(a) 畫一個獨立的「agent 游標」跟著系統游標跑；(b) 只用系統游標，加上視覺提示（halo、pill、click 閃紅）。

## 決策

- 動作走**真實 HID 路徑**：`CGWarpMouseCursorPosition` + `CGEventPost`，與輔助工具/自動化框架同一條路。游標就是使用者的系統游標，看得到、**人類實體輸入隨時優先**（可以直接把滑鼠搶走）。
- presence UI 是**疊加**：移動時軟藍色 halo 環繞系統指標、點擊瞬間紅色 halo、底部霓虹「Agent active — hands off」橫幅。**永遠不畫第二個箭頭**。
- `DH_PRESENCE=0` 可整個關掉；`enable_agent_cursor(True/False)`、`hide_agent_presence()` 控制 lifecycle。

## 取捨

- 歷史上第二個 fake arrow 造成**延遲/不同步**（拖著一個游標跑），被移除。「單一游標 + halo」視覺資訊略少於雙游標方案，但同步永遠完美，因為它們本來就是同一個東西。
- 真實 HID 意味著**動作會搶 focus**（前景輸入）：座標點擊要求目標 app 在前景；「不搶 focus 的背景控制」列為 roadmap 而非現況——文件必須誠實（review #12）。

## 後果

- 「物理輸入優先」成為整個產品的安全底線之一：不管 agent 在做什麼，使用者抓住滑鼠就贏。
- presence 是有狀態、會動的 UI，驗證它**不能靠單張截圖**——衍生出 observe loop 與 ADR-0006 的 main-thread 約束，以及 `docs/OBSERVE-LOOP.md` 中「必須含跨 app 點擊 + 數秒閒置」的驗收清單（此規則來自一次實際出貨的 bug）。
- halo 的顏色語意（藍=移動、紅=點擊）是對外承諾的一部分，改配色前先想清楚。
