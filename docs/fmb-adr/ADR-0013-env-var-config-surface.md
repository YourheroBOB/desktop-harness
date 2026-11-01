# ADR-0013：以 `DH_*` 環境變數作為唯一執行期設定面（不引入設定檔）

- **狀態：** 接受中
- **日期：** 2026-08
- **相關：** `README.md`、`docs/fmb-api/configuration.md`、`docs/fmb/ARCHITECTURE.md` §3.4

## 背景

agent 呼叫 desktop-harness 的方式是 `desktop-harness <<'PY' … PY`——每次都是一個短命程序。傳統「設定檔」模式需要解決：檔案放哪、如何被發現、如何與預設值合併、程序只活幾百毫秒時值不值得解析。與此同時，agent 與 shell 腳本天生擅長環境變數：`DH_NO_DAEMON=1 desktop-harness …` 一行就能改變行為，也最容易在測試裡注入與復原。

## 決策

1. 所有執行期開關以 `DH_` 前綴環境變數暴露：`DH_NO_DAEMON`、`DH_PRESENCE`、`DH_SAFE`、`DH_ALLOW_SENSITIVE`、`DH_MOUSE_INSTANT`、`DH_AUDIT_LOG`、`DH_SOCKET`、`DH_TOKEN_PATH`。
2. 不引入 YAML／TOML 設定檔；變數的權威清單與效果集中在 `docs/fmb-api/configuration.md`。
3. 敏感路徑（socket、token、audit log）也走同一機制覆寫，讓測試能把一切導向 `tmp_path`／tempfile。

## 取捨

- **優點**：與 agent／shell 天然整合；無狀態、無需發現路徑；測試注入與復原容易；`DH_ALLOW_SENSITIVE` 之類高風險開關因為「每次都要顯式 export」而提高誤用門檻。
- **缺點**：開關一多就難以發現（只能靠文件窮舉）；型別全是字串，布林值靠 `"0"`／`"1"` 慣例；環境容易被父程序污染，造成「在我機器上不會」；沒有 schema 驗證。

## 後果

- 新增行為開關優先走 `DH_*`，並同步更新 `docs/fmb-api/configuration.md`；不得為單一功能發明私有設定檔格式。
- 高風險開關（改變安全政策者）必須預設保守：`DH_SAFE` 預設開、`DH_ALLOW_SENSITIVE` 預設關。
- 測試一律用 `DH_SOCKET`／`DH_TOKEN_PATH`／`DH_AUDIT_LOG` 指向臨時目錄，不碰使用者既有 daemon 與真實 log（見 `docs/fmb-perf` 驗證原則）。
