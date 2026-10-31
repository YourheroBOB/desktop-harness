# 03 · 感知與動作（FAQ C1–C9）

## C1 · `labels()` / `ax_snapshot` 是空的（Electron、canvas）

- **問題：** 對某些 app（Electron、網頁 canvas、遊戲）讀不到任何 AX 節點。
- **原因：** 這是 AX-first 架構的**已知限制**：非原生或無正確 accessibility 標註的 UI，AX 樹本來就稀疏或為空（ADR-0001 的明文取捨）。
- **解法：** 退到第 3 層感知——`screenshot(app=…)` 拍視窗 PNG，讓 agent 用視覺讀圖。注意座標點擊前目標 app 要在前景（見 C3）。日常原生 app（Settings、TextEdit、Finder、Safari chrome）不需要此 fallback。
- **相關檔案：** `src/desktop_harness/ax.py`、`src/desktop_harness/capture.py`、`docs/fmb-adr/ADR-0001-ax-first-perception.md`、`RELEASE.md`（known limits）。

## C2 · `click_text` 點錯按鈕（寬鬆匹配）

- **問題：** `click_text("Play")` 結果點到 "Play all" 或 "Playing from"。
- **原因：** 預設 `exact=False` 是子字串匹配；短字詞特別容易配到假朋友。這正是 2026-08-10 媒體事故的根因之一。
- **解法：** 需要精確目標時用 `click_text("Play", role="AXButton", exact=True)`。`find` 的配分已改良為 exact > startswith > 最短子字串，但仍建議關鍵動作（Play/Pause、送出鈕）一律 `exact=True`。
- **相關檔案：** `src/desktop_harness/ax.py`（find 配分）、`src/desktop_harness/helpers.py`、`docs/POSTMORTEM-media-play.md`、`docs/fmb-adr/ADR-0007-media-look-once.md`。

## C3 · 座標點擊沒反應或點到別的視窗

- **問題：** `click(x, y)` 之後目標 app 沒反應，或效果落在別的視窗。
- **原因：** HID 是**前景輸入**路徑——座標點擊要求目標 app 在前景；若被別的視窗蓋住，點擊會落在蓋住的視窗上。「不搶焦點的背景控制」尚未實作（roadmap 項目）。
- **解法：** 先 `activate(<目標 app>)`（或 `open_app`）再點擊；更好的是優先走 `click_text`——有 AX 動作（`AXPress`）時根本不需要座標。SKILL.md 明言「coordinate clicks want the target app frontmost」。
- **相關檔案：** `src/desktop_harness/input.py`、`src/desktop_harness/windows.py`（activate）、`SKILL.md`（Gotchas）、`docs/fmb-adr/ADR-0005-real-hid-single-cursor.md`。

## C4 · `click_text(..., app=<pid>)` 傳整數 pid 時出錯

- **問題：** `ax_snapshot` / `find` 都接受 pid 當 `app` 參數，但 `click_text` 帶 pid 時在座標 fallback 路徑出 `AttributeError`。
- **原因：** pre-release review #6 指出 `click_text` 的 activate fallback 把 pid 直接傳給預期字串的 `find_app`。此問題列於 review；在目前版本使用前請先驗證。
- **解法：** 保守做法：`click_text` 一律傳 app **名稱**（字串），pid 只用在 `ax_snapshot` / `find` 這類讀取型 API。若重現 crash，回報 issue 並附 `--doctor` + `selftest` 輸出。
- **相關檔案：** `src/desktop_harness/helpers.py`、`src/desktop_harness/windows.py`（`find_app`）、`docs/PRE-RELEASE-REVIEW.md`（#6）。

## C5 · `find_app("Text")` 開到不相關的 app

- **問題：** 用短名稱查 app，結果啟動了名稱湊巧包含該字的其他 app。
- **原因：** 舊版 `find_app` 子字串採 first-hit；v0.4.2 已改為精確名稱 → bundle id → 前綴 → 最短子字串的配分排序，但**非常短**的查詢字串仍可能配到非預期結果。
- **解法：** 使用完整 app 名稱（如 `"TextEdit"` 而非 `"Text"`）；必要時先 `list_apps()` 確認名稱再操作。
- **相關檔案：** `src/desktop_harness/windows.py`、`docs/PRE-RELEASE-REVIEW.md`（#7）、`docs/fmb/ARCHITECTURE.md`（§2）。

## C6 · 動作回傳成功但畫面沒變

- **問題：** `click_text` / `set_field` 沒丟例外，agent 向使用者宣稱成功，但畫面根本沒變。
- **原因：** 「沒例外」只代表 **AX 呼叫成功**——按鈕可能 disabled、彈窗可能蓋住、動作可能無效果。這是 ADR-0009 明文規範的核心陷阱。
- **解法：** 任何意在改變畫面的動作後，必須 `verify("預期發生什麼")` 並**讀取它回傳的截圖路徑**，之後才能宣稱成功。純探索呼叫（`labels`、`ax_snapshot`）可豁免。
- **相關檔案：** `src/desktop_harness/helpers.py`（verify）、`SKILL.md`（Verify 段）、`docs/fmb-adr/ADR-0009-verify-after-mutation.md`。

## C7 · 沒有 `menu_click` / `wait_for` / 剪貼簿 helper

- **問題：** 想點選單列（File → Save）、條件等待某文字出現、或讀寫剪貼簿，發現沒有對應 helper。
- **原因：** 這些是 v0.4.2 的**已知能力缺口**（pre-release review #12），`menu_click` 與 `wait_for` 列於 roadmap 前段項目，剪貼簿 helper 亦在 roadmap（含保存／復原與 audit 設計考量）。
- **解法：** 過渡期把任務專用 wrapper 寫在 `agent-workspace/agent_helpers.py`（每次腳本自動載入；改完記得重啟 daemon）。選單可用 `hotkey` 替代；等待可用 `wait` / `wait_stable`＋`find` 輪詢自製。關注 `docs/fmb/ROADMAP.md` 的落地進度。
- **相關檔案：** `agent-workspace/agent_helpers.py`、`docs/fmb/ROADMAP.md`（#2、#3、#4）、`docs/PRE-RELEASE-REVIEW.md`（#12）。

## C8 · `type_text` 長文字很慢

- **問題：** 用 `type_text` 輸入一大段文字耗時很久。
- **原因：** `type_text` 逐字輸入、每字約 8ms 延遲（review #20 列為 medium）——短字串沒問題，長文會線性放大。
- **解法：** 長文字改用剪貼簿貼上路徑（自行以 `pbcopy`＋`hotkey("cmd","v")` 組合；注意剪貼簿是全域共享狀態，需保存／復原並留意敏感內容）。官方 `set_clipboard` / `paste` helper 在 roadmap 中。
- **相關檔案：** `src/desktop_harness/input.py`、`docs/PRE-RELEASE-REVIEW.md`（#20）、`docs/fmb/ROADMAP.md`（#4）。

## C9 · `hotkey("cmd", ".")` 等按鍵無效

- **問題：** 某些鍵（`.`、`/`、F 功能鍵等）的 `hotkey` / `key` 沒作用。
- **原因：** 鍵盤 keycode 對照表未涵蓋全部按鍵（review #12 的能力缺口之一）。
- **解法：** 常見修飾鍵＋字母／數字組合可用；特殊符號鍵可改用 `type_text`（走 unicode 路徑）或在 `agent-workspace` 自訂 wrapper。若業務需要，擴充 keycode 表是小型 PR。
- **相關檔案：** `src/desktop_harness/input.py`、`docs/PRE-RELEASE-REVIEW.md`（#12）。
