# 06 · 開發者與進階（FAQ F1–F7）

## F1 · `voice_session.py` 說缺 `XAI_API_KEY`

- **問題：** 跑語音實驗腳本時直接退出並提示缺 key。
- **原因：** Voice API 需要 **console.x.ai 的 `XAI_API_KEY`**——**Grok Build 的登入（`~/.grok/auth.json`）與 SuperGrok 訂閱都不是 API key**，也不自動附贈 Voice 額度。這是刻意明確退出的設計（不假造存取權）。
- **解法：** (1) 到 console.x.ai 建 key 並 `export XAI_API_KEY=…`（key 存環境變數或 Keychain，**絕不**寫進 repo 檔案）；(2) 沒 key 時用 `--dry-run`（tools-only，`--text` 模式可離線檢視工具定義）；(3) 另需 `pip install websockets sounddevice numpy`。注意此路徑為**實驗性、可選**，不屬於核心安裝。
- **相關檔案：** `scripts/voice_session.py`、`src/desktop_harness/voice_tools.py`、`VOICE.md`、`scripts/voice_hotkey_readme.md`。

## F2 · presence 驗證：單張截圖看起來正常，但其實壞了

- **問題：** 修改 presence UI 後拍一張截圖驗證「有光環有橫幅」，就宣告完成。
- **原因：** presence 是**會動、有狀態**的 overlay，最壞的失敗模式是「在別的視窗搶走焦點的瞬間消失」——這是正常且持續發生的使用情境，不是邊角案例。歷史上真的這樣出過一次貨 bug（2026-08-11：其他視窗成為 key 的瞬間 banner/halo 停止渲染）。
- **解法：** 驗證序列必須包含：(1) 一次點擊落在**別的 app**；(2) 之後**數秒純閒置**；(3) 以**多幀**截圖確認 halo/banner 在兩者之後都還在。用 `./scripts/observe-demo.sh /tmp/dh-observe` 做密集取幀。只在自己 process 裡 demo 會「看起來通過但實際是壞的」。
- **相關檔案：** `docs/OBSERVE-LOOP.md`（presence 檢查清單）、`scripts/observe-demo.sh`、`src/desktop_harness/presence.py`、`SKILL.md`（presence 段）。

## F3 · 程序直接 SIGABRT、沒有任何 Python 例外

- **問題：** 觸碰 presence／視窗相關程式碼後，整個行程直接被 abort，`try/except` 完全接不到。
- **原因：** **AppKit 的 window 方法只能在 main thread 呼叫**——跨執行緒呼叫時 macOS 直接 SIGABRT，不是 Python 例外、無法恢復。已被實際嘗試並確認（ADR-0006）。
- **解法：** 不要開背景執行緒去 pump AppKit／run loop。改在**呼叫執行緒上分片等待**（`presence.keep_alive()` 的模式）。若真的需要背景更新，正確路徑是把 AppKit 呼叫 marshal 回 main thread（目前共識是先不做）。code review 觸碰 AppKit 的 PR 時必問：「這會在哪個 thread 執行？」
- **相關檔案：** `src/desktop_harness/presence.py`（`keep_alive()`）、`docs/fmb-adr/ADR-0006-appkit-main-thread.md`、`docs/OBSERVE-LOOP.md`。

## F4 · 測試如何不污染使用者環境？

- **問題：** 寫測試／驗證腳本時，不想動到使用者真正的 daemon、audit log 與截圖。
- **原因：** 預設路徑都是全域的（`~/.desktop-harness/`、`~/Library/Caches/desktop-harness/`、`$TMPDIR/desktop-harness/`）。
- **解法：** 遵循 `docs/fmb-perf/verification-plan.md` 的共通原則：(1) `DH_SOCKET`／`DH_TOKEN_PATH`／`DH_AUDIT_LOG` 全指向 `tempfile`／`tmp_path`；(2) `DH_NO_DAEMON=1` 避免碰使用者 daemon；(3) 測試前記錄 `daemon status`、測試後確認不變；(4) 不連任何網路正式服務（voice 用假 WS server 或 `--dry-run`）；(5) 假憑證一律用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串，不使用真實格式前綴。
- **相關檔案：** `docs/fmb-perf/verification-plan.md`、`src/desktop_harness/daemon.py`、`src/desktop_harness/safety.py`。

## F5 · `$TMPDIR/desktop-harness/` 的截圖 PNG 一直累積

- **問題：** 長跑 daemon 或 observe loop 後，暫存目錄裡的 `capture-<pid>-<ns>.png` 無限增加。
- **原因：** 截圖檔名已改為每次唯一（解決併發覆蓋問題），但**沒有清理機制**——檔案只增不減（fmb-perf PERC-3，P1 級已知問題）。另外 `--doctor` 寫固定的 `dh-doctor.png`，併發執行會互相覆蓋（PERC-4，P2）。
- **解法：** 短期手動清 `$TMPDIR/desktop-harness/`。長期修法（啟動時清理舊 capture、上限內保留新檔）在 fmb-perf 建議中。
- **相關檔案：** `src/desktop_harness/capture.py`（`TMP`）、`src/desktop_harness/admin.py`（doctor 固定檔名）、`docs/fmb-perf/findings-perception.md`（PERC-3/4）。

## F6 · 多螢幕下 presence 光環位置不對

- **問題：** 外接螢幕上，halo 與實際游標位置有偏移。
- **原因：** presence overlay 的多螢幕座標轉換**未保證**——known limit（review #12 列有「document main display only or fix transform」）。
- **解法：** 目前保守做法：presence 相關驗證在**主顯示器**上進行。跨螢幕的控制動作本身（CGEvent 路徑）不受影響，受影響的是視覺提示的位置。修復列於 roadmap 類項（誠實標示覆蓋率優先於宣稱支援）。
- **相關檔案：** `src/desktop_harness/presence.py`、`docs/PRE-RELEASE-REVIEW.md`（#12）、`docs/fmb/ARCHITECTURE.md`（§5）。

## F7 · 各文件版本號看起來不一致（歷史問題）

- **問題：** 在舊文件或網路文章中看到 v0.1／v0.3／v0.4 互相矛盾的說法。
- **原因：** 歷史包袱：早期 `__init__.py`、`pyproject.toml` 與 README 版本不同步、roadmap 表過時（pre-release review #3，列為 critical 的 release hygiene 問題）。
- **解法：** v0.4.2 已統一：`src/desktop_harness/__init__.py` 與 `pyproject.toml` 皆為 `0.4.2`，`desktop-harness --version` 為準。閱讀舊文件時以 `DESIGN.md`／`README.md` 現況與 ADR 為準；升級方式見 `README.md`（git pull → `./install.sh`，**無靜默自動更新**——會動滑鼠的程式碼由使用者決定何時更新）。
- **相關檔案：** `src/desktop_harness/__init__.py`、`pyproject.toml`、`README.md`（Updating 段）、`docs/PRE-RELEASE-REVIEW.md`（#3）。
