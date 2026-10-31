# 現況盤點：日誌、指標、錯誤回報

> 基於 repo v0.4.2 可見檔案（`src/desktop_harness/*.py`、`docs/fmb/ARCHITECTURE.md`、`docs/PRE-RELEASE-REVIEW.md`）整理。
> 原則：只記錄「看得見的現況」，推測部分標注來源。

## 1. 一句話結論

**有一層薄薄的審計影子（`safety.audit` → `audit.jsonl`），但沒有體系化的日誌、完全沒有指標、錯誤回報是 ad-hoc 的 print / 例外。** 目前出了問題，只能靠人類看終端機輸出。

## 2. 逐元件盤點

| 元件 | 現有日誌 | 現有指標 | 錯誤回報 | 主要缺口 |
|------|----------|----------|----------|----------|
| `run.py`（CLI 入口） | stdout/stderr，人類可讀 | 無 | 例外 + process exit code | stdin 腳本內容若被印出就是重大洩漏；無耗時、無路由決策紀錄 |
| `daemon.py` | **無** | 無 | **無** | 無請求日誌、無 ping 計時；stale socket 無任何訊號（REVIEW #10） |
| `helpers.py` | 間接（透過 `safety.audit`） | 無 | 例外傳播 | 一次操作多次 AX walk 卻無計時（REVIEW #9） |
| `ax.py` | 無 | 無 | 例外 | 無節點數／耗時／截斷資訊 |
| `input.py` | 無 | 無 | 例外 | 固定 sleep 主導延遲卻不可觀測（REVIEW #13） |
| `capture.py` | `safety.audit("screenshot", {"app","window_id","path"})` | 無 | `RuntimeError` | 無位元組數／耗時；完整路徑含 `$TMPDIR`（可能含 uid 資訊） |
| `safety.py` | `audit.jsonl`：`{"ts","event","detail"}` | 無 | `PermissionError` | 覆蓋面不全（REVIEW #1）；無輪替／redaction（REVIEW #18）；寫入失敗靜默 |
| `presence.py` | 無 | 無 | 無 | overlay 異常（例如历史上 focus 被搶就不渲染）無訊號 |
| `admin.py`（`--doctor`） | stdout 的 `[PASS]/[FAIL]` | 無 | FAIL 計數 + 設定 pane 提示 | 結果不留檔、無歷史趨勢，無法回答「昨天是好的嗎」 |
| `selftest.py` | stdout | 無 | 同上 | 同上 |
| `demo.py` | stdout | 無 | 例外 | 同上 |
| `voice_session.py`（實驗性） | stdout/stderr | 無 | `print` + `sys.exit(2)` | 金鑰相關錯誤只走 stderr；dry-run 行為與文件不符（REVIEW #22） |

## 3. 既有審計機制的細節（`safety.py`，可見程式碼）

```python
_AUDIT = Path(os.environ.get("DH_AUDIT_LOG",
    Path.home() / ".desktop-harness" / "audit.jsonl"))

def audit(event: str, detail: dict | None = None) -> None:
    try:
        _AUDIT.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(), "event": event, "detail": detail or {}}
        with _AUDIT.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass        # ← 觀測性黑洞：失敗無聲
```

依 `docs/fmb/ARCHITECTURE.md` 與 `capture.py`，目前已發出的事件約有：`activate`、`click_text`、`screenshot`、`ensure_media_playing`。

**現況優點（保留）：**
- JSONL 格式、路徑可用 `DH_AUDIT_LOG` 覆寫、安全閘門（`check_app_allowed` / `check_frontmost_allowed`）已有明確的 raise 點。

**現況缺口（要補）：**

| # | 缺口 | 對應 review / roadmap |
|---|------|------------------------|
| G1 | 審計只覆蓋部分 mutation，`click`/`type_text`/`hotkey`/`set_field` 未全數入 log | PRE-RELEASE-REVIEW #1 |
| G2 | `audit()` 寫入失敗完全靜默 | 新發現 |
| G3 | 無輪替、無保留策略、無 redaction 文件 | PRE-RELEASE-REVIEW #18、ROADMAP #7 |
| G4 | 無任何耗時／節點數／位元組數指標 | PRE-RELEASE-REVIEW #9、#13 |
| G5 | daemon 無請求層觀測（含 0.4s ping 痛點） | PRE-RELEASE-REVIEW #10 |
| G6 | `--doctor`／`selftest` 結果不留痕，無趨勢 | 新發現 |
| G7 | 沒有「禁止入欄」的敏感清單與掃描機制 | 新發現（本設計 `SENSITIVE-FIELDS.md` 補） |
| G8 | `time.time()` 單一時基、無 monotonic，無法可靠算耗時 | 新發現 |

## 4. 錯誤回報現況

- **傳播方式：** 例外直接拋給 CLI 程序 → stderr traceback → 非零 exit。
- **沒有：** 錯誤分類（permission / timeout / AX-failure / not-found）、錯誤碼、關聯 id、重試訊號。
- **後果：** 無法回答「這台機器上週有多少次因 Accessibility 未授權而失敗」「哪個 action 最常 miss」。
- **本設計對策：** 見 `EVENTS.md` 的 `error` 事件與 `error_class` 枚舉、`METRICS-SLO.md` 的 `dh_errors_total{class,module}`。

## 5. 小結

現有 `audit.jsonl` 是正確的第一塊磚，但它薄、靜默、無輪替、無指標、無儀表板。本可觀測性設計以它為地基，向外延伸出「事件 → 指標 → SLO → 告警 → 儀表板」五層，並用一份嚴格的敏感欄位政策把整條鏈條鎖在隱私紅線之內。
