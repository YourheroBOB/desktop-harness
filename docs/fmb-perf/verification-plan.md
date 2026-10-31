# 驗證方案（不觸碰正式服務、不寫 repo 外路徑）

本目錄所有 finding 的驗證共通原則與具體沙箱設定。**所有驗證都可以在本機完成，零網路連線、零正式服務。**

---

## 1. 環境隔離矩陣

現行程式碼已提供足夠的環境變數做沙箱，不需修改原始碼即可隔離測試：

| 用途 | 環境變數 | 沙箱值 |
|------|----------|--------|
| daemon socket／pid | `DH_SOCKET` | `<tmp>/test.sock` |
| daemon token | `DH_TOKEN_PATH` | `<tmp>/test.token` |
| audit log | `DH_AUDIT_LOG` | `<tmp>/audit.jsonl` |
| 強制 in-process（不碰使用者 daemon） | `DH_NO_DAEMON` | `1` |
| 截圖暫存（需 monkeypatch `capture.TMP`） | — | `tmp_path` |
| 假 API key（voice 測試） | `XAI_API_KEY` | `FAKE_VALUE_FOR_TEST` |

`tmp` 一律來自 `tempfile.TemporaryDirectory()` 或 pytest `tmp_path`。**測試前先記錄真實 `daemon status`，測試後確認不變**（目前 selftest 違反此點 → TR-6）。

---

## 2. 各修復項的回歸清單

### DAEMON-1／2（P0 PR）

```python
with tempfile.TemporaryDirectory() as tmp:
    env = {**os.environ, "DH_SOCKET": f"{tmp}/t.sock", "DH_TOKEN_PATH": f"{tmp}/t.token"}
    # 啟 daemon 子進程（-m desktop_harness.run daemon start --bg, env=env）
    # T1: client connect 後沉默 → 另一 client ping 應於 ~5s 內成功
    # T2: client 送 ping 後立即 close → daemon 存活（重複 20 次）
    # T3: 正常 exec roundtrip 仍工作
    # T4: 壞 JSON → 得到 {"ok":false,...}，daemon 存活
```

### DAEMON-3／4（P1 PR）

```python
# D3: exec_via_daemon("import time; time.sleep(30)", timeout=3)
#     → 修後 ~3s 收到 exec timeout 錯誤，隨後 ping 立即成功
# D4: touch <tmp>/t.sock（無 daemon）→ is_running() ≤0.15s 回 False
```

### PERC-1／2／3（P1 PR）

```python
# P1: 計時 list_apps() 快取前後（1000 次呼叫）
#     activate 輪詢 monkeypatch 驗證不再走 list_apps
# P2: _match_window 純函式單測（fake window list：pid/exact/substring 優先級）
# P3: tmp_path 放 300 個假 capture-*.png + 不相關檔案 → sweep →
#     斷言只刪自家模式、上限內新檔保留
```

### TR-1／2／3（P1 PR，voice）

```python
# 本機假 WS server：websockets.serve 於 127.0.0.1 臨時 port（測試自起）
# T1: 接受連線後不回應 → 15s open/idle timeout 生效
# T2: 拒絕連線 → 3 次重試 + backoff（fake clock 斷言間隔）
# T3: fake execute = time.sleep(2)，期間併發送 delta 事件 → 仍被處理
# T4: 假 server 連送 20 輪 function-call/done → 第 8 輪後停止
# 全程 XAI_API_KEY=FAKE_VALUE_FOR_TEST，絕不連 api.x.ai
```

### TR-4／OBS-1（P1 PR，audit + daemon log）

```python
# audit: monkeypatch open 拋 OSError → stderr 警告出現且不 crash
#        6MB 假檔 → rotate 產生 .1，內容保留
# daemon log: 7 個混合請求 → 恰 7 行 JSONL，stats op 計數一致
```

---

## 3. 手動煙霧驗證（修復後跑一輪）

1. `desktop-harness --doctor` — 全 PASS（PERC-4 修改後路徑唯一）
2. `desktop-harness selftest` — 全 PASS，且 daemon 對照項（OBS-4）印出兩個耗時
3. `desktop-harness daemon start --bg` → 連續 10 個 `desktop-harness <<'PY' print(labels()[:3]) PY` — 每步 < 150ms 體感、daemon log（OBS-1）有 10 行 exec 記錄
4. `kill <daemon-pid>`（SIGTERM）→ `daemon status` 立即正確反映已停（DAEMON-6）
5. `desktop-harness demo` — 人眼確認 presence 行為未受影響（若動到任何 presence 相關路徑，**必須**按 `docs/OBSERVE-LOOP.md` 的多幀 + 跨 app click + 數秒 idle 檢查表驗證，不可只看單張截圖）

---

## 4. 明確不做的事（邊界）

- 不連 `api.x.ai` 或任何網路服務做驗證（voice 全走假 server／dry-run）
- 不讀寫 repo 外路徑（`/tmp` 沙箱除外，用 `tempfile`）
- 不修改 `.github/workflows`、secrets、git 設定
- 測試假憑證一律 `FAKE_VALUE_FOR_TEST`，不使用任何真實格式前綴
- 不把任何 token、客戶資料、訊息內容寫進本目錄文件
