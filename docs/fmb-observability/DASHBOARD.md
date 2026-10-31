# 儀表板版面規格

> 型態：**單頁、純本機產生**（`desktop-harness report` 提案指令，或先用 `jq` 腳本產出同等 Markdown）。
> 原則：所有 panel 只顯示彙總值；任何「內容」都留在使用者機器上、不進報告。

## 1. 整體版面

```
┌──────────────────────────────────────────────────────────────┐
│ desktop-harness observability report                          │
│ 版本 v0.4.2 · 窗口 24h · 產出於 <mono_ms> · SLO 版本 v0.1      │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│ P1 健康       │ P2 延遲       │ P3 可靠性     │ P4 安全          │
├──────────────┴──────────────┴──────────────┴─────────────────┤
│ P5 daemon                       │ P6 隱私合規                   │
├─────────────────────────────────┴──────────────────────────────┤
│ 建議動作（連結 ROADMAP / ALERTS）                                │
└──────────────────────────────────────────────────────────────┘
```

## 2. Panel 規格

### P1 健康（更新：每次 report）

| 元素 | 來源 | 形式 |
|------|------|------|
| doctor 最近 5 次 | `doctor_check` 事件 | 燈號表：`[PASS][PASS][FAIL]…` |
| selftest 最近結果 | `selftest_step` | 最後一筆總狀態 |
| 權限狀態 | `doctor_check{name=Accessibility/Screen Recording}` | PASS/FAIL + 提示文字 |

### P2 延遲（更新：每日；視覺：ASCII 長條）

| 列 | 指標 | 為何重要 |
|----|------|----------|
| CLI cold | `dh_cli_duration_ms{mode=inprocess}` p50/p95 | 沒開 daemon 的代價 |
| CLI via daemon | `dh_cli_duration_ms{mode=daemon}` p50/p95 | 溫熱路徑的體驗線 |
| ping | `dh_daemon_ping_ms` p95 | REVIEW #10 的驗收指標 |
| `ax_snapshot` | `dh_action_duration_ms{action=ax_snapshot}` | 主要「眼睛」成本 |
| `click_text` | `dh_action_duration_ms{action=click_text}` | 主要「手」成本 |
| `screenshot` | `dh_action_duration_ms{action=screenshot}` | 回落路徑成本 |

範例（假資料）：

```
p95 延遲（ms）
inprocess CLI │████████████████████░░░░░░  1850  (SLO-2 ✓)
daemon CLI    │██████░░░░░░░░░░░░░░░░░░░░   520  (SLO-1 ✓)
daemon ping   │█░░░░░░░░░░░░░░░░░░░░░░░░░    18  (SLO-3 ✓)
ax_snapshot   │████░░░░░░░░░░░░░░░░░░░░░░   240  (SLO-4 ✓)
click_text    │███░░░░░░░░░░░░░░░░░░░░░░░    96  (SLO-1 ✓)
screenshot    │█████████░░░░░░░░░░░░░░░░░   410  (—)
```

### P3 可靠性（更新：每日）

| 元素 | 來源 |
|------|------|
| 各 action 的 result 分佈（ok / fallback_xy / miss / blocked / error） | `dh_action_result_total` |
| `click_text` 首次 AX 命中率 vs SLO-5 | 同上比值 |
| error class Top 5（只有 class + module，**沒有訊息**） | `dh_errors_total{class,module}` |
| 重複 AX walk 計數 | `dh_ax_walks_total`（REVIEW #9 的證據） |

### P4 安全（更新：每次 report）

| 元素 | 來源 |
|------|------|
| blocks by gate/reason | `dh_safety_blocks_total` |
| override 使用次數（非 0 即解釋） | `dh_safety_overrides_total` |
| **閘門完整性檢查結果**（SLO-8，必須 0） | §2 比對邏輯，見 `ALERTS.md` |

### P5 daemon（更新：每次 report）

| 元素 | 來源 |
|------|------|
| requests by op / ok-rate | `dh_daemon_requests_total` |
| ping p95 | `dh_daemon_ping_ms` |
| stale socket 次數 | `dh_daemon_stale_socket_total` |
| 本次 uptime | `dh_daemon_uptime_ms` |

### P6 隱私合規（更新：每次 report）

| 元素 | 來源 |
|------|------|
| forbidden 樣式掃描結果（必須 0） | 對 events.jsonl 樣本跑 `SENSITIVE-FIELDS.md` §4 樣式 |
| redaction 計數（restricted 被 hash 掉幾次） | redaction 層計數 |
| 事件檔輪替狀態／大小 | 檔案系統（本機） |

### 頁尾：建議動作

依當日違反的 SLO／告警，輸出對應 ROADMAP 項次（例：`SLO-3 未達 → ROADMAP #8`）。報告只放連結與編號，**不複製個案內容**。

## 3. 每日報告檔頭範例（假資料）

```markdown
# desktop-harness report — 2026-08-12（窗口 24h）
版本 v0.4.2 · SLO 版本 v0.1 · 事件 1,204 筆 · 指標快照 96 筆
資料檔：~/.desktop-harness/{events,metrics}.jsonl（大小 1.2MB / 0.3MB）
硬紅線：gate_bypass=0 ✓ · forbidden_hits=0 ✓ · audit_write_failures=0 ✓
```

## 4. 明確不做

- 不在儀表板放任何截圖、AX 樹、輸入文字、視窗標題。
- 不做多機彙總視圖（每台 Mac 獨立報告）。
- 不做即時串流面板；本地工具的合理頻率是「跑一次看一次」。
