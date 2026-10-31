# ADR-0003：以「任意 Python script」作為 agent 介面

**狀態：** 接受中（附帶明確的爆炸半徑認知）  
**相關模組：** `run.py`、`daemon.py`（exec 路徑）、`helpers.py`（namespace）、`agent-workspace/agent_helpers.py`

## 背景

如果介面是固定的一組工具函式，agent 每多一個需求就要改 harness、加 API、更新 skill。而 agent 本身就會寫 Python。把整個 helper namespace 直接放進一個可執行的 script 環境，等於讓 agent 拿到一個「可組合的手」，而不是一盒固定的手。

## 決策

介面是 `exec` 一段 agent 提供的 Python：

```bash
desktop-harness <<'PY'
open_app("TextEdit")
click_text("Format")
PY
```

- `helpers.py` 提供 public surface，script 執行時所有 helper 都在 scope 內。
- `agent-workspace/agent_helpers.py` 是**agent 可自行編輯**的擴充點，每次 script 執行時自動載入；核心原語則固定在 `desktop_harness.helpers`，兩者分層。
- daemon 路徑（ADR-0004）用同樣的 exec 語意：`{"op":"exec","code":"…"}`。

## 取捨

- **能力上限極高**（可組合、可臨時包裝、可 `import` 標準庫）對上**無法在介面層限權**：script 裡可以 `import subprocess`、寫檔案、直接呼叫 Quartz，繞過所有 helper 級的安全 gate。這是**刻意**的設計，不是疏漏。
- 因此安全模型分兩層：runtime 只擋得了 helper 路徑上的行為（敏感 app gate、daemon token）；其餘靠 **skill 政策**（「送訊息/付款/刪除前必須先問人」）與**人類監督**。`SECURITY.md` 明言這點：「DH_* gates only wrap a few helpers」。
- 代價是**文件必須誠實**：不能宣稱「safe mode 保证安全」。行銷語言與現實的落差曾被 code review 列為 critical 問題。

## 後果

- 擴充新能力通常**不需要改核心**：在 `agent-workspace` 寫 wrapper 即可。
- 任何「安全強化」若只包 helper，都擋不住 exec 直呼系統——評估安全議題時永遠從「攻擊者有一個帶 Accessibility 權限的 Python 執行環境」出發。
- `check_helper_allowed()` 目前是為未來高風險 helper（如 `run_shell`）預留的 hook，核心套件刻意**不**內建任何 shell escape helper。
- unattended / always-approve 執行時，建議用非管理者帳號或專用 agent profile（見 `SECURITY.md`）。
