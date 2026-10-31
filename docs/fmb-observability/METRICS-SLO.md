# 指標與 SLO 設計

> 本機優先：指標落地為 `~/.desktop-harness/metrics.jsonl`，由 `desktop-harness report`（提案指令）本地彙總。
> 不送任何外部服務。SLO 數值為**初期基線提案**，需經 §4 的基線收集後校正。

## 1. 本機指標模型

```
counter   單調累加（重啟歸零，靠 report 做增量視窗）
gauge     當前值快照（如最近一次 ax_snapshot 節點數）
histogram 固定分桶 + count，report 端算 p50/p95/max
```

flush 時機（提案）：程序結束、或每 60s、或 daemon 每 500 請求——取先到者。

metrics.jsonl 行格式：

```json
{"ts_ms": 1754899200000, "name": "dh_action_duration_ms", "type": "histogram",
 "labels": {"action": "click_text", "route": "daemon"},
 "count": 24, "p50_ms": 38, "p95_ms": 96, "max_ms": 210, "buckets_ms": {"50": 20, "100": 3, "250": 1}}
```

labels 只放低基數列舉值（action/result/route/op/class…），**不放 app 名稱等高基數維度**（避免日誌爆炸與間接識別）。

## 2. 指標清單

### 2.1 呼叫與延遲

| 指標 | 型別 | labels | 來源事件 |
|------|------|--------|----------|
| `dh_cli_invocations_total` | counter | `mode`(inprocess/daemon) | `cli_invoke` |
| `dh_cli_duration_ms` | histogram | `mode` | `cli_invoke`→`cli_exit` |
| `dh_action_duration_ms` | histogram | `action`(activate/click_text/ax_snapshot/ax_find/screenshot/type_text/set_field/media_transport)、`route` | 各動作事件 |
| `dh_daemon_ping_ms` | histogram | — | `daemon_request{op=ping}` |
| `dh_daemon_probe_ms` | histogram | — | `cli_invoke.daemon_probe_ms` |

### 2.2 可靠性

| 指標 | 型別 | labels | 來源事件 |
|------|------|--------|----------|
| `dh_action_result_total` | counter | `action`、`result`(ok/fallback_xy/miss/blocked/error) | 各動作事件 |
| `dh_ax_nodes` | gauge | `interactive_only` | `ax_snapshot.nodes_count` |
| `dh_ax_walks_total` | counter | `reason`(find/find_miss_retry/sample) | `ax_snapshot.walks`（對應 REVIEW #9：找出重複走訪） |
| `dh_screenshot_bytes` | gauge | — | `screenshot.bytes` |
| `dh_errors_total` | counter | `class`、`module` | `error` |
| `dh_doctor_checks_total` | counter | `status`(pass/fail) | `doctor_check` |

### 2.3 安全與隱私

| 指標 | 型別 | labels | 來源事件 |
|------|------|--------|----------|
| `dh_safety_blocks_total` | counter | `gate`、`reason` | `safety_block` |
| `dh_safety_overrides_total` | counter | — | `safety_override` |
| `dh_gate_bypass_events_total` | counter | — | 「block 之後仍發生 mutation」= **必須為 0**（對應 REVIEW #1） |
| `dh_forbidden_field_hits_total` | counter | `field` | 隱私自掃命中（見 `SENSITIVE-FIELDS.md`） |
| `dh_audit_write_failures_total` | counter | `target` | `audit_write_failed` |

### 2.4 daemon 健康

| 指標 | 型別 | labels | 來源事件 |
|------|------|--------|----------|
| `dh_daemon_requests_total` | counter | `op`、`ok` | `daemon_request` |
| `dh_daemon_stale_socket_total` | counter | — | `daemon_stale_socket` |
| `dh_daemon_uptime_ms` | gauge | — | `daemon_start`→`daemon_stop` |

## 3. SLO 提案（初期基線，待校正）

> 單機工具沒有流量 SLO；以下為「每次操作的體驗線」與「正確性紅線」。窗口：每日報告。

| ID | SLO | 目標（初值） | 度量 | 未達處置 |
|----|-----|--------------|------|----------|
| SLO-1 | daemon 路徑端到端延遲 | p95 ≤ 600 ms（不含 app 自身動畫） | `dh_action_duration_ms{route=daemon}` p95 | 查 AX 重複走訪（REVIEW #9）、固定 sleep（REVIEW #13） |
| SLO-2 | in-process 冷啟動 | p95 ≤ 2000 ms | `dh_cli_duration_ms{mode=inprocess}` | pyobjc import 成本；建議多用 daemon |
| SLO-3 | daemon ping | p95 ≤ 100 ms | `dh_daemon_ping_ms` | 落地 ROADMAP #8（0.4s → 50–100ms） |
| SLO-4 | `ax_snapshot` 延遲 | p95 ≤ 300 ms | `dh_action_duration_ms{action=ax_snapshot}` | 樹大小／`max_nodes` 設定 |
| SLO-5 | `click_text` 首次 AX 命中率 | ≥ 90%（fallback ≤ 10%） | `dh_action_result_total{action=click_text}` | 調整 `find` 評分；fallback 過多代表 AX 路徑退化 |
| SLO-6 | 截圖成功率 | ≥ 99% | `dh_action_result_total{action=screenshot}` | Screen Recording 授權、視窗生命週期 |
| SLO-7 | doctor 全項通過率 | 每次執行都應全過；任何 fail 即事件 | `dh_doctor_checks_total{status=fail}` = 0 | 見 ALRT-01 |
| SLO-8 | 安全閘完整性 | `dh_gate_bypass_events_total` = 0（硬紅線） | block 後 mutation 比對 | 見 ALRT-04／REVIEW #1 |
| SLO-9 | 隱私合規 | `dh_forbidden_field_hits_total` = 0（硬紅線） | 每次 report 自掃 | 見 ALRT-06 |
| SLO-10 | 整體錯誤率 | error/總動作 ≤ 1% | `dh_errors_total` / `dh_action_result_total` | 依 `error_class` 分群排查 |

## 4. 基線收集與校正流程

1. **收集期 2 週**：只開 `events.jsonl` + `metrics.jsonl`（預設最小集，不含 restricted 欄位）。
2. **每日跑 `desktop-harness report`**（提案指令）產出 `DASHBOARD.md` 版面。
3. 用實測 p50/p95 取代 §3 的「初值」，修訂本文件為 v0.2，並在 report 中標註「SLO 版本」。
4. 任何 SLO 調整都要記 ADR（architecture decision record，放 `docs/fmb-observability/` 或 BOB 指定的決策檔）。

## 5. 明確不做

- 不上報任何外部 metrics endpoint（隱私與「不連正式服務」硬規則）。
- 不做 per-app 維度指標（高基數 + 間接識別風險）。
- 不把截圖位元組數與「截了什麼」放在同一行（前者是容量訊號，後者永遠不入欄）。
