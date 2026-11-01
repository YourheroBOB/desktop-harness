# desktop-harness API 參考（`docs/fmb-api/`）

本目錄是 desktop-harness 的**公開介面參考**：CLI 指令、Python helper 函式、daemon 通訊協定、實驗性語音工具，以及環境設定項。適用版本：**v0.4.2**。

> 這些文件只描述「怎麼呼叫」與「行為契約」。設計理念、安全模型與架構背景請看 [DESIGN.md](../../DESIGN.md)、[ARCHITECTURE.md](../fmb/ARCHITECTURE.md)、[SECURITY.md](../../SECURITY.md)。

## 簽名與內容來源說明

- 本參考的函式簽名、參數與回傳，係依據 repo 內**公開文件**（`README.md`、`SKILL.md`、`DESIGN.md`、`docs/fmb/ARCHITECTURE*.md`、`HOW_IT_WORKS.md`、`VOICE.md`、各 ADR）與**代表性呼叫點**（`src/desktop_harness/demo.py`、`scripts/observe-demo.sh`、`scripts/voice_session.py`）整理。
- 精確的型別標註、預設值與少數仍在微調的回傳結構，**以 `src/desktop_harness/` 原始碼為準**；本文件在對應處以「依實作」標注。
- 文件內**不出現任何真實 token、金鑰、密碼或個資**；範例中需要假憑證時一律使用 `FAKE_VALUE_FOR_TEST`。

## 文件索引

| 檔案 | 內容 |
|------|------|
| [cli.md](./cli.md) | `desktop-harness` CLI 指令與子命令（`--doctor`、`selftest`、`demo`、`skill`、`daemon`、`check-update`、stdin 腳本） |
| [helpers.md](./helpers.md) | 腳本命名空間中的公開 helper 函式（探索／感知／操作／媒體／滑鼠／鍵盤／截圖／presence／驗證） |
| [configuration.md](./configuration.md) | 環境變數與設定項（僅列變數名與效果） |
| [daemon-protocol.md](./daemon-protocol.md) | 常駐 daemon 的 NDJSON-over-Unix-socket 協定與 Python API |
| [voice-tools.md](./voice-tools.md) | 實驗性語音控制：Realtime WebSocket 端點、工具 schema 與本機執行器 |

## 三條使用契約（呼叫前必讀）

1. **AX 優先**：能用 `labels`／`find`／`click_text` 就不要截圖（見 [ADR-0001](../fmb-adr/ADR-0001-ax-first-perception.md)）。
2. **變更後務必 `verify()`**：動作沒拋錯只代表 AX 呼叫成功，不代表畫面如預期（見 [ADR-0009](../fmb-adr/ADR-0009-verify-after-mutation.md)）。
3. **媒體 look-once / act-once**：先讀狀態、只做一次動作，絕不連按空白鍵（見 [ADR-0007](../fmb-adr/ADR-0007-media-look-once.md)、[POSTMORTEM](../POSTMORTEM-media-play.md)）。

## 快速範例

```bash
# 看前景 app 與前 15 個標籤
desktop-harness <<'PY'
print(frontmost_app())
print(labels()[:15])
PY

# 開 App 並依名稱點擊
desktop-harness <<'PY'
open_app("TextEdit")
click_text("Format")
PY
```

完整語法與參見 [cli.md](./cli.md) 與 [helpers.md](./helpers.md)。
