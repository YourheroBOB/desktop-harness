# desktop-harness 效能與可靠性改善待辦清單（Remediation Backlog）

- **日期：** 2026-08
- **用途：** 整合既有 `findings-*.md` 與 `findings-entrypoints.md`，產出**可排程、可驗收**的改善清單。
- **repo：** YourheroBOB/desktop-harness @ v0.4.2
- **性質：** 僅文件，未修改任何原始碼。
- **排序原則：** P0（止血）→ P1（近期迭代）→ P2（打磨）。同級內以「工作量小、效益高」優先。

---

## 一、P0：立即止血（會導致 daemon 掛死或崩潰）

| ID | 標題 | 位置 | 一句話修法 | 驗收標準 |
|----|------|------|-----------|---------|
| DAEMON-1 | 單執行緒 accept 迴圈 + 無連線逾時 | `daemon.py` | `conn.settimeout(5.0)`；為每個連線 spawn handler（或至少確保不阻塞 accept） | 模擬 client 連上後不送資料：daemon 仍可接受新連線 |
| DAEMON-2 | 連線處理未捕捉例外終結 daemon | `daemon.py` | `serve()` 主迴圈加 `try/except Exception`，單一連線失敗不得中斷監聽 | 對連線注入壞 payload / 強制斷線：daemon 繼續 serve |

---

## 二、P1：近期迭代（明顯效能損失／可靠性缺口）

### 2.1 daemon 穩定性與延遲

| ID | 標題 | 位置 | 建議修法 | 驗證方式 | 工作量 |
|----|------|------|---------|---------|--------|
| DAEMON-3 | `exec` 無伺服端逾時 | `daemon.py` | 為 exec 引入 `signal.alarm` 或 watchdog thread，逾時回傳 `{ok: false, error: "timeout"}` 並保留 daemon | 執行 `import time; time.sleep(60)` 腳本，驗證 30s 後回傳且 daemon 存活 | S |
| DAEMON-4 | `is_running()` 0.4s ping 拖慢降級 | `daemon.py` / `run.py` | ping timeout 降至 0.1s；connect 前先讀 PID 檔檢查行程存活；連線失敗且行程已死則刪 stale socket+pid | daemon 未啟動時，`time desktop-harness <<'PY' pass PY` 總耗時 < 0.3s | S |

### 2.2 感知與截圖

| ID | 標題 | 位置 | 建議修法 | 驗證方式 | 工作量 |
|----|------|------|---------|---------|--------|
| PERC-1 | `find_app` 每次完整 NSWorkspace 列舉 | `windows.py` | 加入 100–200ms TTL cache，key=`(query, allow_prefix)`；或至少區分「已快取 app 清單」與「前景查詢」 | `timeit` 比較 100 次 `find_app("Safari")`；對照修改前 | S |
| PERC-2 | `capture.screenshot` 每次全量列舉視窗 + 子串 first-hit | `capture.py` | 快取 `CGWindowListCopyWindowInfo`（短 TTL）；改精確/前綴匹配優先於子字串 | 併發兩個不同 app 截圖，驗證不會互相覆蓋且匹配正確 | S |
| PERC-3 | 截圖暫存檔永不清理 | `capture.py` | 輕量 sweep：每次呼叫時清理超過 24h 的 `capture-*.png`；或 daemon 啟動時清一次 | 在 `tmp_path` 造 25h 前的假 PNG，呼叫 screenshot 後驗證被刪 | S |

### 2.3 voice / 腳本層

| ID | 標題 | 位置 | 建議修法 | 驗證方式 | 工作量 |
|----|------|------|---------|---------|--------|
| ENTRY-1 | WS 無逾時 | `scripts/voice_session.py` | `open_timeout=5.0`；事件迴圈加 idle timeout | mock server 不回應，驗證腳本退出 | S |
| ENTRY-2 | `execute()` 阻塞事件迴圈 | `scripts/voice_session.py` | `await asyncio.to_thread(execute, ...)`；注意 AppKit main-thread | mock execute sleep 2s，測事件迴圈響應 | S–M |
| ENTRY-3 | 無重試退避 | `scripts/voice_session.py` | `connect_with_retry()`，指數退避；區分可重試/不可重試 | mock 前兩次拒絕第三次成功 | S |
| TR-4 | `audit()` 靜默吞例外、無輪替 | `safety.py` | `audit()` 區分 `OSError`/`TypeError`；超過 5MB 輪替為 `.1` | 造 6MB 假 log，驗證輪替；造唯讀目錄，驗證不會崩 | S |

---

## 三、P2：打磨項（可觀測性、邊界、測試隔離）

| ID | 標題 | 位置 | 建議修法 | 驗證方式 |
|----|------|------|---------|---------|
| DAEMON-5 | `daemon start` TOCTOU 雙实例 | `daemon.py` | `O_EXCL` lock 檔或 PID 檔 atomic create；或 accept loop bind 前二次確認 | 併發兩個 `daemon start`，驗證只有一個成功 |
| DAEMON-6 | SIGTERM 不留清理 | `daemon.py` | 註冊 `signal.signal(SIGTERM, handler)`，handler 內 `finally` 清理 socket/pid | 送 SIGTERM，驗證 socket/pid 被刪 |
| DAEMON-7 | 請求 buffer 無上限、token 非 constant-time | `daemon.py` | `MAX_REQ_BYTES = 1MB`；`hmac.compare_digest()` 比較 token | 送 2MB payload，驗證被拒；計時側信道（optional） |
| PERC-4 | doctor 固定路徑 `dh-doctor.png` | `admin.py` | 改用 `tempfile.NamedTemporaryFile` 或 `capture-<pid>-<ns>.png` | 併發兩個 `--doctor`，驗證不互相覆蓋 |
| PERC-5 | `activate` 忙等輪詢 + 重複 activate | `windows.py` | 輪詢間隔從 80ms 放寬到 150–200ms；已前景則跳過 activate | 計時 `activate` 已知前景 app；觀察 NSWorkspace 呼叫次數 |
| TR-3 | voice 自動續 turn 無上限 | `scripts/voice_session.py` | `max_turns=10` | mock 持續 function call，驗證 N 輪後停止 |
| TR-5 | helpers/input 固定 sleeps | `helpers.py` / `input.py` | 條件等待取代固定 sleep（見 ENTRY-4） | 慢機器測試成功率 |
| TR-6 | selftest 停掉使用者 daemon | `selftest.py` | 測試前記錄 `daemon status`，測試後還原；或強制 `DH_NO_DAEMON=1` | 執行 selftest，驗證既有 daemon 不受影響 |
| ENTRY-4 | demo 固定 sleep | `demo.py` | 條件等待 | 慢機器測試 |
| ENTRY-5 | demo 無錯誤恢復 | `demo.py` | try/finally + 明確錯誤 | mock open_app 失敗 |
| ENTRY-6 | voice 無結構化日誌 | `scripts/voice_session.py` | logging 模組 + 事件分類 | 執行後檢查日誌格式 |
| ENTRY-7 | voice 無 turn 上限 | `scripts/voice_session.py` | max_turns | mock 持續 call |
| ENTRY-8 | observe-demo.sh 無清理 | `scripts/observe-demo.sh` | mktemp + trap | 執行後檢查殘留 |
| OBS-1 | daemon 零請求日誌 | `daemon.py` | 每請求記 `op`、`duration_ms`、`ok`、`error`；可選 `DH_DAEMON_LOG` 路徑 | 發送 ping/exec，驗證 log 出現對應行 |
| OBS-2 | audit 覆蓋不完整 | `safety.py` / `helpers.py` | 補齊 `set_field`、`scroll`、`drag` 等高風險 helper | 執行各 helper，驗證 audit log |
| OBS-3 | voice print 無結構 | `scripts/voice_session.py` | logging | 見 ENTRY-6 |
| OBS-4 | selftest 缺 daemon 對照 | `selftest.py` | 印出「daemon roundtrip ms」與「in-process ms」 | 執行 selftest，驗證輸出兩組數字 |

---

## 四、建議執行節奏

```
【第一週：P0 + 快速 P1】
  ├─ DAEMON-1, DAEMON-2（daemon 不掛死）
  ├─ DAEMON-4（ping 延遲，S 級立即見效）
  ├─ PERC-3（截圖清理，S 級）
  ├─ ENTRY-1, ENTRY-3（voice 逾時 + 重試，S 級）
  └─ TR-4（audit 輪替，S 級）

【第二～三週：核心 P1】
  ├─ DAEMON-3（exec 逾時）
  ├─ ENTRY-2（voice 非阻塞，需評估 AppKit 決策點）
  ├─ PERC-1, PERC-2（感知快取）
  └─ OBS-1（daemon 日誌，讓上述改善可觀測）

【第四週起：P2 打磨】
  ├─ 測試隔離（TR-6, PERC-4）
  ├─ 條件等待取代 sleep（ENTRY-4, TR-5）
  ├─ 安全閘門清理（對應 ROADMAP 第 9 項）
  └─ voice 結構化日誌與 turn 上限（ENTRY-6, ENTRY-7）
```

---

## 五、決策點（需要 BOB 拍板）

1. **voice `execute()` 背景化 vs AppKit main-thread（ENTRY-2）**
   - 若 `execute()` 會觸發 presence overlay 或截圖（AppKit），`asyncio.to_thread` 可能違反 ADR-0006。
   - **保守建議：** voice session 啟用時設定 `DH_PRESENCE=0`，並在文件註明「voice 模式不保證 presence UI」；或維持單一 worker thread 序列執行。
2. **截圖清理策略（PERC-3）**
   - 清理 24h 前的檔案 vs daemon 啟動時全清。**保守建議：** 只清 24h 前，避免誤刪同 session 並發截圖。
3. **daemon 請求日誌預設開或關（OBS-1）**
   - 記日志有極輕微 I/O 成本。**保守建議：** 預設開啟，路徑 `~/.desktop-harness/daemon.log`，並提供 `DH_DAEMON_LOG=0` 關閉。
4. **voice `max_turns` 預設值（ENTRY-7）**
   - 太小會中斷正常多步任務，太大失去保護意義。**保守建議：** 預設 10，並可透過環境變數 `GROK_VOICE_MAX_TURNS` 覆寫。
