# ADR-0015：明確非目標——範圍護欄與「我們不做什麼」

- **狀態：** 接受中
- **日期：** 2026-08
- **相關：** `DESIGN.md`、`RELEASE.md`、`docs/fmb/ROADMAP-ZH-TW.md`、[ADR-0011](./ADR-0011-core-zero-network.md)

## 背景

這個產品的能力面（真實滑鼠＋鍵盤＋讀屏）天然會吸引「順便做成 X」的請求：通用 computer-use 複製品、CAPTCHA 破解、預設沙盒、綁定語音、自動更新。每一項都會改變信任模型或法律風險輪廓。與其每次爭論，不如把界線寫成決策。

## 決策

以下為明確非目標（整理自 `DESIGN.md`「Explicit non-goals」與各路線圖文件的一致表述）：

1. **不複製任何 proprietary computer-use 產品**；不追求功能清單對齊。
2. **預設不做沙盒／VM 隔離**：這是驅動真實 Mac 的工具，安全模型是「同意＋閘門＋人類可搶控制權」，不是隔離。
3. **不取代 shell／git／API 等正常開發工作**：GUI 路徑只在任務真的是 GUI 時使用（效率契約，見 [ADR-0001](./ADR-0001-ax-first-perception.md)）。
4. **不做 CAPTCHA／Cloudflare bypass 類功能**（`RELEASE.md` 明言）。
5. **不靜默自動更新**；**不把語音實驗升級為核心依賴**（見 [ADR-0011](./ADR-0011-core-zero-network.md)）。
6. **不鎖定單一 agent 品牌**：為 Grok Build 打造，但任何能跑 shell 的 agent 都能用（見 [ADR-0002](./ADR-0002-cli-not-mcp.md)）。

## 取捨

- **優點**：範圍可預期、審核請求有依據、新進者不會把精力花在錯誤議題上；「不做」和「做」一樣需要文件，否則會被反覆重新提問。
- **缺點**：可能擋掉原本有價值的相鄰市場（例如企業 VM 場景）；非目標會隨產品成熟過期，需要定期重審而非一次定終身。

## 後果

- PR 若實質跨越任一條非目標，應先開 ADR 修訂非目標，再寫程式；不要在 PR 描述裡默默擴大範圍。
- 非目標條文與 `RELEASE.md`、`ROADMAP-ZH-TW.md` 必須保持一致；改一處要同步其餘。
