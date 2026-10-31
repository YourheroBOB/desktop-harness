# ADR-0008：敏感 app 的 runtime 阻擋 + 審計日誌

**狀態：** 接受中（截圖納入阻擋是後補的關鍵推廣）  
**相關模組：** `safety.py`、`windows.py`（activate/open_app）、`capture.py`、`input.py`/`ax.py`（變異動作）

## 背景

harness 能控制真實桌面，密碼管理器類 app（1Password、Bitwarden、Keychain…）若被 agent 點擊/輸入/截圖，等於把最敏感的憑證暴露給 exec 環境。早期版本只在 `activate`/`open_app` 檢查（review critical #1）：敏感 app **已經**在前景時，`click_text`/`type_text`/截圖全都暢通。

## 決策

雙重 gate，由 `safety.py` 集中實作：

1. **名稱 gate**（`check_app_allowed`）：`activate`/`open_app`/`screenshot(app=…)` 對敏感名稱/bundle substring（1password、bitwarden、keychain、lastpass、keepass、dashlane、nordpass、enpass、secrets、wallet、bank…）拒絕。
2. **前景 gate**（`check_frontmost_allowed`）：所有**變異動作**（點、輸入、hotkey、set_field）在敏感 app 為 frontmost 時拒絕——因為攻擊面不只「打開它」，還有「它已經開著」。

**截圖與點擊同級**：`screenshot` 在未指定 app 或全螢幕時也跑前景 gate——「拍下畫面上的密碼」與「點進密碼欄位」是同一等級的洩漏。這是本 ADR 最重要的一條推廣。

- 逃生口：`DH_ALLOW_SENSITIVE=1`（明確、單一、不建議常開）。
- 審計：關鍵變異寫 `~/.desktop-harness/audit.jsonl`（`DH_AUDIT_LOG` 可覆寫）。
- 刻意**不內建** shell escape helper（見 ADR-0003）；`check_helper_allowed` 是為未來預留。

## 取捨

- substring 阻擋（名稱與 bundle）會誤傷（如名稱含 "bank" 的無害 app）；精確清單（bundle id exact）誤傷少但漏新工具。現況選 substring + 可覆寫，並在 review 中已知此為 medium 級 trade-off。
- gate 只保護 **helper 路徑**；exec 直呼系統繞得過（ADR-0003 的既定界限）。安全是「分層的摩擦」，不是邊界。
- 審計不記錄 `set_field` 的**值**（避免把密碼寫進 log），只記動作與目標。

## 後果

- 修改任何「新的變異動作」時，**必須**加上對應 gate 呼叫——這是隱含的 coding 規範，本 ADR 將其顯性化。
- 敏感清單的擴充（名稱 + bundle 兩個 tuple）是低風險、高價值的常見 PR 類型。
- 審計日誌無 rotation/redaction 機制（review #18），長期 agent 會無限增長——列為已知債。
