# ADR-0007：媒體控制「先讀狀態、只做一次動作」

**狀態：** 接受中（2026-08-10 事故後固化，見 `docs/POSTMORTEM-media-play.md`）  
**相關模組：** `helpers.py`（`media_transport` / `ensure_media_playing`）、`ax.py`（`find` 配分）

## 背景

一次真實事故：使用者說「播畫面上的歌」，agent 先正確播放，然後**暫停**，再**播放**，最後**跳到別首歌**。根因是複合的：

- Space 鍵是 **toggle**——連按會把剛播的又暫停；
- 寬鬆字串匹配把 `"Play"` 配到 **Playing from**／**Play all**；
- **Pause 已可見（= 正在播）** 卻仍繼續搜尋 Play；
- 部分成功後在一個 turn 內重試 3–4 種點擊策略。

## 決策

媒體操作強制「look-once, act-once」狀態機：

```text
read media_transport()
if playing → done（什麼都不做）
if paused  → 按一次 exact Play → 再讀一次 → done
else       → 回報 unknown，不亂試
```

落實為：

- `media_transport()` 回報 `{state, transport_play, row_play, play}`，且 `play == transport_play`（selftest 有斷言）——粗配到的 row 級 Play 不算數。
- `ensure_media_playing()`：看到 Pause 就 noop。
- `click_text(..., exact=True)` + `find` 的配分改良（exact > 短字假朋友，`Play` 不再配到 `Play all`）。
- skill 明文禁止：spam Space／media keys、一 turn 多策略重試、未經明確要求就換歌或點 Play all。

## 取捨

- 「慢半拍先讀狀態」比「直接按了再說」多一次 AX walk；換來**幂等**與不破壞使用者當下狀態。
- 狀態機遇到非標準 transport UI 會回 `unknown` 而非猜——寧可回報失敗，不可盲目 act。這是刻意選的保守面。

## 後果

- 此模式被推廣為通用原則：**任何 toggle 語意的控制（不只是媒體）都必須先讀狀態**，因為「再試一次」在 toggle 上等於「再做一次反效果」。
- `find` 的配分規則（exact > startswith > 最短 substring）成為所有文字配對的基準，`find_app` 也遵循同樣的排序（見 `windows.py`）。
- 教訓類化：**部分成功後的直覺是重試，但正確動作是 verify**（→ ADR-0009）。
