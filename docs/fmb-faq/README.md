# desktop-harness FAQ 與疑難排解（docs/fmb-faq）

> 本目錄整理使用者與開發者最常見的問題與疑難排解，基於 repo `YourheroBOB/desktop-harness` @ v0.4.2 的文件與程式碼現況撰寫。每一題包含：**問題、原因、解法、相關檔案**。
>
> 閱讀順序建議：先跑 `desktop-harness --doctor` 與 `desktop-harness selftest`，再按分類找題目。深層設計原因請參考 `docs/fmb-adr/`（架構決策紀錄）與 `docs/fmb-perf/`（效能審查）。

## 分類索引

| 檔案 | 主題 | 題數 |
|------|------|------|
| [01-install-and-permissions.md](./01-install-and-permissions.md) | 安裝、PATH、Accessibility / Screen Recording 權限 | 8 |
| [02-cli-and-daemon.md](./02-cli-and-daemon.md) | CLI heredoc 用法、warm daemon 啟停與疑難 | 8 |
| [03-perception-and-actions.md](./03-perception-and-actions.md) | AX 感知、點擊、打字、座標與 helper 缺口 | 9 |
| [04-media-and-players.md](./04-media-and-players.md) | 媒體播放控制（含 2026-08-10 事故教訓） | 3 |
| [05-safety-and-audit.md](./05-safety-and-audit.md) | 敏感 app 阻擋、audit log、daemon 安全 | 6 |
| [06-dev-and-advanced.md](./06-dev-and-advanced.md) | 開發者：voice、presence、測試隔離、已知債 | 7 |

## 快速對照表（全部題目）

| ID | 問題摘要 |
|----|----------|
| A1 | `desktop-harness: command not found` |
| A2 | `--doctor` 顯示 Accessibility FAIL |
| A3 | `--doctor` 顯示 Screen Recording FAIL / 截圖空白 |
| A4 | `--doctor` 顯示 pyobjc 匯入失敗 |
| A5 | Screen Recording 已授權但截圖仍失敗 |
| A6 | `desktop-harness skill` 在非 checkout 環境失敗（歷史） |
| A7 | 第一次 CLI 呼叫特別慢 |
| A8 | 可以在 Linux / 舊 macOS 上跑嗎 |
| B1 | heredoc 腳本沒輸出或語法錯 |
| B2 | daemon start 後 status 仍是 stopped / 第二次 start 被拒 |
| B3 | 每次呼叫都多等約 400ms |
| B4 | daemon 突然整個無回應 |
| B5 | 改了 `agent-workspace/agent_helpers.py` 沒生效 |
| B6 | 想強制不走 daemon |
| B7 | 跑 selftest 後 daemon 被停掉了 |
| B8 | daemon 的 socket / token 檔在哪、測試怎麼隔離 |
| C1 | `labels()` / `ax_snapshot` 是空的（Electron、canvas） |
| C2 | `click_text` 點錯按鈕（寬鬆匹配） |
| C3 | 座標點擊沒反應或點到別的視窗 |
| C4 | `click_text(..., app=<pid>)` 傳整數 pid 時出錯 |
| C5 | `find_app("Text")` 開到不相關的 app |
| C6 | 動作回傳成功但畫面沒變 |
| C7 | 沒有 `menu_click` / `wait_for` / 剪貼簿 helper |
| C8 | `type_text` 長文字很慢 |
| C9 | `hotkey("cmd", ".")` 等按鍵無效 |
| D1 | 「播畫面上的歌」結果被暫停又跳歌 |
| D2 | `media_transport()` 回 `state: unknown` |
| D3 | 想暫停正在播放的媒體 |
| E1 | `open_app("1Password")` 被拒絕 |
| E2 | 敏感 app 已在前景時，點擊／截圖也被擋 |
| E3 | 名稱含 "bank" / "wallet" 的無害 app 被誤擋 |
| E4 | `audit.jsonl` 無限成長 |
| E5 | 誰能連上 daemon？共享機器安全嗎 |
| E6 | 可以開 always-approve / 無人值守嗎 |
| F1 | `voice_session.py` 說缺 `XAI_API_KEY` |
| F2 | presence 驗證：單張截圖看起來正常但其實壞了 |
| F3 | 程序直接 SIGABRT、無 Python 例外 |
| F4 | 測試如何不污染使用者環境 |
| F5 | `$TMPDIR/desktop-harness/` 的截圖 PNG 一直累積 |
| F6 | 多螢幕下 presence 光環位置不對 |
| F7 | 各文件版本號看起來不一致（歷史） |

## 一般排障順序（建議）

1. `desktop-harness --doctor` — 權限與相依健檢，先修第一個 FAIL。
2. `desktop-harness selftest` — 非破壞性功能自測。
3. `desktop-harness demo` — 肉眼確認滑鼠移動與 TextEdit 打字。
4. 仍異常 → 依上表找對應題目；涉及設計取捨的看 `docs/fmb-adr/`。
