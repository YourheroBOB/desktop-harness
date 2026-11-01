# ADR-0010：外送／破壞性動作的「同意閘」放在 agent 政策層，而非 runtime 程式碼

- **狀態：** 接受中
- **日期：** 2026-08
- **相關：** [ADR-0003](./ADR-0003-arbitrary-exec-surface.md)、[ADR-0008](./ADR-0008-sensitive-app-gates.md)、`SKILL.md`、`SECURITY.md`

## 背景

desktop-harness 有能力代表使用者發訊息、購買、刪除、修改安全設定。這一類動作的風險不在「按到哪個像素」，而在「這個操作的語意」——而語意存在於 agent 的任務上下文裡，不存在於 AX 樹裡。對 runtime 而言，`click_text("Send")` 與 `click_text("Save")` 在結構上幾乎同構。

文件一貫要求這類動作必須先取得人類同意：

- `SKILL.md`：「Real Mac. **STOP and ask** before: messages, posts, purchases, deletes, security settings, passwords.」
- `SECURITY.md`：「Agents should refuse outbound actions (messages, purchases, deletes) without human confirmation」
- `README.md`：「**Agents must ask** before send/post/pay/delete/security changes」

與此同時，runtime 能可靠判斷的只有「目標是不是敏感 app」「前景是不是敏感 app」（ADR-0008）以及把動作寫進審計日誌。`docs/fmb/ROADMAP.md` 亦指出：`safety.check_helper_allowed()` 曾是未接線的死 API，`_HIGH_RISK_HELPERS` 清單內的名稱並非真實 helper——在程式碼層列舉「高風險函式」既維護不動，也容易給人錯誤的安全感。

## 決策

1. 外送／破壞性動作的同意閘實作在 **agent 政策層**：`SKILL.md` 的規則條款加上 `SECURITY.md` 的建議，由 agent 在呼叫前自行判斷並向人類確認。
2. runtime 安全柵欄只做它能確定判斷的事：敏感 app 阻擋（開啟／聚焦／前景變更／截圖）、審計日誌、權限邊界（socket 0600 + token）。runtime **不**嘗試從 helper 名稱或參數推測「這個意圖是否危險」。
3. 不宣稱 harness 能「防止」危險動作。文件明確寫出：任意 `exec` 是產品特性，腳本可 `import subprocess` 繞過 `DH_*` 閘門，風險由使用者承擔。

## 取捨

- **優點**：不會誤擋合法操作；規則可隨 agent 能力快速演進，不必改版；人類只在不確定時被打斷。
- **缺點**：這是「政策」不是「機制」，沒有硬保證——故障或惡意的 agent 可以不遵守；`DH_ALLOW_SENSITIVE=1` 一類覆寫會放大失誤後果；審計是事後而非事前。

## 後果

- 新進開發者必須理解安全模型是**分層**的：runtime gate（機制）＋ agent policy（政策）＋ 人類物理控制權（隨時可搶滑鼠）。三者疊加，任何一單獨一層都不是完整答案。
- 「強化安全」的提案若只能在程式碼層列舉高風險函式名稱，應優先移除或接線到真實語意（ROADMAP 第 6 項），而不是讓死 API 繼續製造安全感。
- `SKILL.md`、`SECURITY.md` 必須維持這段誠實邊界的描述；弱化這段描述等同縮小產品的安全宣稱，需另走 ADR。
