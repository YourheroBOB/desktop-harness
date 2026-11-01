# ADR-0014：`agent-workspace/agent_helpers.py` 是唯一官方擴充點

- **狀態：** 接受中
- **日期：** 2026-08
- **相關：** [ADR-0003](./ADR-0003-arbitrary-exec-surface.md)、`docs/fmb/ARCHITECTURE.md`

## 背景

每個使用者／每個 agent 的任務形狀不同：有人要一鍵開「系統設定 → 螢幕保護程式」，有人要一套固定的播放流程。把這些包進 `helpers.py` 會讓核心無限膨脹、merge 衝突不斷，也會把任務特定的假設混進安全邊界之內。

## 決策

1. 核心原典（`open_app`、`click_text`、`labels`、`media_transport` …）保持在 `desktop_harness` 套件內，跨任務通用、經過安全閘門與審計。
2. 任務特定的包裝一律放 `agent-workspace/agent_helpers.py`；該檔由 repo 提供骨架（目前只有 docstring 與註解範例），由 agent／使用者編輯。
3. 每個腳本組裝命名空間時自動併入 `agent_helpers`，因此腳本不需 import 即可呼叫自訂 helper。

## 取捨

- **優點**：核心保持穩定可升級；客製碼跟著 clone 走、可 review；任務知識與引擎分離。
- **缺點**：擴充碼運行在與核心相同的任意 exec 權限內（沒有額外沙箱），`agent_helpers.py` 本身就是可信程式碼；載入它是每個腳本的固定成本，檔案壞掉會影響所有腳本（載入路徑需 fail-safe，細節以 `helpers.py` 實作為準）。

## 後果

- 新進者的第一課應該是「先寫 `agent_helpers.py`，不要急著改 `helpers.py`」。
- 依 `pyproject.toml` 的打包設定（wheel 只收 `src/desktop_harness`），`agent-workspace/` 不在 wheel 內——以安裝版使用時不會自動獲得它，文件需誠實標示。
