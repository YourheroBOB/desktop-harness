# 04 · 媒體與播放器（FAQ D1–D3）

> 本分類濃縮自 2026-08-10 的真實事故（`docs/POSTMORTEM-media-play.md`）與 ADR-0007。媒體控制是 **toggle 語意**的典型：「再試一次」常等於「再做一次反效果」。

## D1 · 「播畫面上的歌」結果被暫停、又播放、最後跳到別首歌

- **問題：** 請 agent 播放媒體，結果一連串操作把剛播的又暫停，甚至換了歌。
- **原因：** 複合根因：(1) Space 是 **toggle**，連按會反覆切換；(2) 寬鬆匹配 `"Play"` 配到 "Play all"／"Playing from"；(3) **Pause 已可見（= 正在播）**卻仍繼續找 Play；(4) 部分成功後在一個 turn 內重試 3–4 種點擊策略。
- **解法：** 強制 look-once / act-once：
  ```text
  read media_transport()
  if playing → done（什麼都不做）
  if paused  → 按一次 exact Play → 再讀一次 → done
  else       → 回報 unknown，不要亂試
  ```
  實務上直接用 `ensure_media_playing(app?)`；手動按時用 `click_text("Play", role="AXButton", exact=True)`。**永遠不要**用 `hotkey("space")` 或媒體鍵「萬用試一遍」。
- **相關檔案：** `src/desktop_harness/helpers.py`（`media_transport` / `ensure_media_playing`）、`docs/POSTMORTEM-media-play.md`、`docs/fmb-adr/ADR-0007-media-look-once.md`、`SKILL.md`（Media 段）。

## D2 · `media_transport()` 回 `state: unknown`

- **問題：** 讀播放器狀態得到 `unknown`，不確定該做什麼。
- **原因：** 該播放器的 transport UI 不符合標準模式（transport 級 Play 偵測不到）；狀態機刻意設計為「寧可回報 unknown 也不猜」（ADR-0007 的保守面）。注意回傳中的 `play == transport_play`——粗配到的 row 級 Play 不算數（selftest 有此斷言）。
- **解法：** `unknown` 時**不要盲目 act**。用 `labels()` / `ax_snapshot` 看該 app 的按鈕，找到明確的 transport Pause／Play 再以 `exact=True` 按一次；或截圖讓 agent 視覺判讀。仍無法判定就回報使用者。
- **相關檔案：** `src/desktop_harness/helpers.py`、`src/desktop_harness/selftest.py`（`play == transport_play` 斷言）、`docs/fmb-adr/ADR-0007-media-look-once.md`。

## D3 · 想暫停正在播放的媒體

- **問題：** 使用者要求暫停，agent 不確定怎麼安全地做。
- **原因：** 暫停同樣是 toggle——不讀狀態就按，可能把已暫停的又播起來。
- **解法：** 同樣 look-once：先 `media_transport()` 確認 `playing`，再按一次**精確**的 Pause（`click_text("Pause", role="AXButton", exact=True)`），然後 `verify()`。換歌或 "Play all" 需要**明確的使用者要求**，不可自行推斷。
- **相關檔案：** `src/desktop_harness/helpers.py`、`SKILL.md`（Media 規則 6）、`docs/POSTMORTEM-media-play.md`。
