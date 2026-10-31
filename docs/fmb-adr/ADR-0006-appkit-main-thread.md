# ADR-0006：AppKit main-thread 約束——分片 wait，不用背景執行緒

**狀態：** 接受中（以一次實際 SIGABRT 證據固化）  
**相關模組：** `presence.py`（`keep_alive()`）、所有 AppKit 呼叫點

## 背景

presence overlay（NSWindow/NSView 系）需要在 agent **閒置**（兩步之間等待）期間持續渲染。直覺解法是開背景執行緒定時 pump run loop。但 AppKit 的 window 方法**只能在 main thread 呼叫**：違反時整個 process 直接 **SIGABRT**——不是 Python 例外，無法捕捉、無法恢復。這被實際嘗試並確認過（紀錄在 `docs/OBSERVE-LOOP.md`）。

## 決策

- **禁止**為了「閒置期間持續更新」而開背景執行緒碰 AppKit。
- 改為**在呼叫執行緒上分片等待**：把長 wait 切成小段，每段之間 pump 主 run loop（`presence.keep_alive()` 即此模式）。
- 任何 presence 修正 PR 的驗收必須包含「跨 app 點擊 + 之後數秒純閒置」的序列（否則只覆蓋「動作中」而漏掉「閒置中」——後者才是真實 agent 使用的主要狀態）。

## 取捨

- 分片 wait 佔用呼叫執行緒、寫起來比 thread 醜；換來**零 SIGABRT 風險**與可預測的單執行緒模型。
- 若未來真的需要背景更新，正確路徑是把 AppKit 呼叫 marshal 回 main thread（如 `performSelectorOnMainThread` / queue），而不是直接跨執行緒呼叫——但目前的共識是先不做。

## 後果

- 任何新 code 觸碰 AppKit（capture、presence、windows 都會）時，code review 必須問一句：「這會在哪個 thread 執行？」
- daemon 是單執行緒 accept loop，exec 也在同一執行緒跑——這與本 ADR 相容，但意味著 daemon 不並發；多個 agent 同時連線會序列化。
- 觀察 loop 工具（`scripts/observe-demo.sh`）的存在就是為了抓這類「只有多影格才看得到」的問題。
