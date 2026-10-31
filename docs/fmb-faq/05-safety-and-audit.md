# 05 · 安全與審計（FAQ E1–E6）

## E1 · `open_app("1Password")` 被拒絕

- **問題：** 呼叫 `open_app` / `activate` 開啟密碼管理器類 app 時丟 `PermissionError`。
- **原因：** 這是**設計行為**：`safety.check_app_allowed()` 對敏感名稱／bundle 子字串（1password、bitwarden、keychain、lastpass、keepass、dashlane、nordpass、enpass、secrets、wallet、bank…）預設拒絕（ADR-0008 的名稱 gate）。
- **解法：** 預設尊重阻擋。真的需要時，明確設定 `DH_ALLOW_SENSITIVE=1`（單一逃生口，SECURITY.md 明言勿隨意開）。
- **相關檔案：** `src/desktop_harness/safety.py`、`docs/fmb-adr/ADR-0008-sensitive-app-gates.md`、`SECURITY.md`。

## E2 · 敏感 app 已在前景時，點擊／截圖也被擋

- **問題：** 沒有「開啟」敏感 app，它本來就在前景，但 `click_text` / `type_text` / `screenshot` 仍被拒。
- **原因：** 同樣是設計行為：前景 gate（`check_frontmost_allowed`）會在**所有變異動作**與**未指定 app 的截圖**前檢查 frontmost 是否為敏感 app——「拍下畫面上的密碼」與「點進密碼欄位」被視為同一等級的洩漏（ADR-0008 最關鍵的推廣）。
- **解法：** 這是安全決策，勿繞過。確有需求時 `DH_ALLOW_SENSITIVE=1` 並全程監督。開發者注意：**新增任何變異動作 helper 時必須掛上對應 gate 呼叫**。
- **相關檔案：** `src/desktop_harness/safety.py`、`src/desktop_harness/capture.py`（截圖 gate）、`docs/fmb-adr/ADR-0008-sensitive-app-gates.md`。

## E3 · 名稱含 "bank" / "wallet" 的無害 app 被誤擋

- **問題：** 某個與金融無關、但名稱含敏感子字串的 app 被拒絕控制。
- **原因：** 敏感清單採**子字串**匹配，刻意偏向誤傷而非漏抓（ADR-0008 已知 trade-off；review #19 建議改以 bundle id 精確匹配，列於 roadmap 安全項）。
- **解法：** 短期：該次操作用 `DH_ALLOW_SENSITIVE=1`。長期：roadmap 建議把清單改以 bundle id 為主，降低誤傷——屬低風險高價值 PR。
- **相關檔案：** `src/desktop_harness/safety.py`（`_SENSITIVE_NAME_SUBSTR`）、`docs/fmb/ROADMAP.md`（#6）、`docs/PRE-RELEASE-REVIEW.md`（#19）。

## E4 · `audit.jsonl` 無限成長

- **問題：** 長時間使用後 `~/.desktop-harness/audit.jsonl` 越來越大。
- **原因：** 目前**沒有輪替與保留政策**（review #18 / fmb-perf OBS-2，已知債）。audit 只記事件與目標、不記 `set_field` 的值（避免把密碼寫進 log），但檔案仍會無限增長。
- **解法：** 手動清理或輪替；測試時用 `DH_AUDIT_LOG` 指到暫存路徑。大小門檻輪替（如 5MB 改名 `.1` 保留 N 份）在 roadmap 中列為 S 級工作。
- **相關檔案：** `src/desktop_harness/safety.py`（audit）、`docs/fmb/ROADMAP.md`（#7）、`docs/fmb-perf/findings-observability.md`。

## E5 · 誰能連上 daemon？共享機器安全嗎？

- **問題：** 想評估把 daemon 開著的風險。
- **原因：** daemon 是「**本機特權 exec 端點**」：能連上 socket 並持有 token 的**同 UID 行程**可執行任意 Python（含滑鼠鍵盤與 AX）。防護是 socket 與 token 皆 0600——防其他使用者，**防不了同帳號下的惡意程式**（它本來就有同等權限，ADR-0004 的明文界限）。
- **解法：** 單人機器風險可接受；**多人共用機器不建議開著 daemon**。長 session 結束後 `desktop-harness daemon stop`。另請記住：任意 exec 是產品特性，`DH_*` 閘門只包住少數 helper 路徑，腳本可 `import subprocess` 繞過（ADR-0003）。
- **相關檔案：** `src/desktop_harness/daemon.py`、`SECURITY.md`、`docs/fmb-adr/ADR-0004-warm-daemon-token-auth.md`、`docs/fmb-adr/ADR-0003-arbitrary-exec-surface.md`。

## E6 · 可以開 always-approve / 無人值守執行嗎？

- **問題：** 想讓 agent 全自動跑 Mac 控制任務。
- **原因：** 這是在真實桌面上跑帶 Accessibility 權限的任意 Python——爆炸半徑是整個使用者帳號。
- **解法：** SECURITY.md 的建議：(1) 執行前審閱 agent 腳本；(2) unattended 堖用**非管理者帳號／專用 agent profile**；(3) 保持敏感 app 預設阻擋；(4) agent 對「送訊息／貼文／購買／刪除／安全設定」必須先問人（skill 政策）。物理輸入隨時優先——抓住滑鼠就能打斷。
- **相關檔案：** `SECURITY.md`、`SKILL.md`（Consent 段）、`src/desktop_harness/safety.py`（`CONFIRM_GUIDANCE`）、`docs/fmb-adr/ADR-0005-real-hid-single-cursor.md`。
