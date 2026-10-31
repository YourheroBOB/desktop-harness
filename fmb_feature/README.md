# fmb_feature — `wait_for`：無競態的 UI 輪詢（v0.4.3 候選）

本目錄只包含**新增檔案**，未修改 repo 內任何既有檔案。

## 為什麼挑這一件（範圍可控、價值明確）

`docs/PRE-RELEASE-REVIEW.md` 的能力缺口表把這件事列為 High：

> No `wait_for(text/role, timeout=)` — Fixed `wait()` races

現況是兩難：

| 做法 | 問題 |
|------|------|
| `wait(0.5)` 固定睡眠 | 慢，而且**還是會 race**（冷啟動 app 常常 >0.5s） |
| 動作後直接 `find()` 讀一次 | 讀太早就是丟硬幣；`SKILL.md` 已經要求「verify, don't assume」，但缺少便宜的工具 |

`SKILL.md` 要求 agent 在每個改變畫面的動作後 `verify()`，可是沒有「等一下直到畫面真的變了」的原語，agent 只能睡久一點或重試到手軟（review #13 也指出固定 sleep 主導了多步延遲）。

這個模組補上那個原語：**有 deadline 的輪詢**，並且刻意做成純 stdlib、可注入 clock／sleep、可離線測試。

## 檔案

| 檔案 | 角色 |
|------|------|
| `fmb_feature/dh_wait.py` | 實作。純 stdlib，不 import pyobjc、不讀寫檔案、不連網 |
| `fmb_feature/test_dh_wait.py` | 單元測試（`unittest`，pytest 也可收），全部注入 fake clock，不會真的睡 |
| `fmb_feature/README.md` | 本文件：用法、整合建議 patch、決策點 |

## 跑測試

```bash
# 兩種都可
python3 -m unittest discover -s fmb_feature -p 'test_*.py' -v
python3 fmb_feature/test_dh_wait.py
```

不需要 macOS、不需要 pyobjc、不需要網路、不寫入 repo 以外路徑（測試連 `tmp_path` 都沒用到）。

## 現在就能用（不動既有檔案）

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("/path/to/desktop-harness") / "fmb_feature"))
from dh_wait import wait_for, wait_for_change, wait_until_gone
```

在 harness 腳本裡：

```bash
desktop-harness <<'PY'
import sys; sys.path.insert(0, "/path/to/desktop-harness/fmb_feature")
from dh_wait import wait_for, wait_for_change

# 1) 點下去之後，等「畫面真的變了」再截圖
before = labels(app="System Settings")
click_text("Privacy & Security", app="System Settings")
res = wait_for_change(lambda: labels(app="System Settings"), before, timeout=3.0)
print("changed:", res.ok, "attempts:", res.attempts, f"{res.elapsed:.2f}s")

# 2) 等某個控制項出現（回傳 node，不是 bool）
node = wait_for(lambda: find("Allow", app="System Settings"), timeout=4.0)
if not node:
    print("Allow button never appeared; screenshot instead:", screenshot(app="System Settings"))
else:
    click_text("Allow", app="System Settings")
PY
```

> 注意：`find` / `labels` / `screenshot` 是 `desktop_harness.helpers` 既有的東西（見 `SKILL.md`），本模組不重新實作它們，只負責「輪詢到對為止」。

## API

| 函式 | 行為 | 成功時的 `value` |
|------|------|------------------|
| `wait_until(pred)` | 輪詢到 `pred()` 為 truthy | 命中的值 |
| `wait_for(match)` | 同上，語意是「等某個 node 出現」 | 命中的 node |
| `wait_until_gone(pred)` | 輪詢到 `pred()` 為 falsy（spinner／sheet 消失） | 最後觀察到的 falsy 值（通常 `None`） |
| `wait_for_change(snap, baseline)` | 輪詢到 snapshot 與 baseline 不同 | 新的 snapshot |
| `wait_stable(snap, settle=2)` | 輪詢到連續 `settle` 次觀測一致 | 穩定下來的 snapshot |
| `Deadline(timeout)` | 多步流程共用的時間預算 | — |

`WaitResult(ok, value, attempts, elapsed, last_error)`：`bool(result)` 就是 `ok`；`result.unwrap()` 成功回值、失敗丟 `TimeoutError`（訊息含 attempts／elapsed／最後例外）。失敗時 `value` 保留**最後看到的樣子**，方便寫「本來應該出現 X，實際看到 Y」。

共同參數：`timeout=5.0`、`interval=0.1`、`backoff=1.5`、`max_interval=0.5`、`clock`、`sleep`、`errors=(Exception,)`。

### 語意與邊界（實測過的行為）

- **至少輪詢一次**：條件已成立時 0 次 sleep，直接回傳 `attempts=1, elapsed=0.0`。
- **絕不超過 deadline**：最後一次 sleep 會被夾到剩餘時間；到期後不再睡，回 `ok=False`。
- **間隔成長**：`interval × backoff` 遞增，上限 `max_interval`（若 `max_interval < interval` 會自動夾到 `interval`）。
- **最小間隔 1ms**：`interval=0` 不會變 busy loop。
- **例外處理**：符合 `errors` 的例外視為一次失敗並重試（AX 在 app 切換時常 transient 失敗），最後一個錯誤放在 `last_error`；`errors=()` 可完全關閉吞例外，讓錯誤立刻冒出來。
- **truthiness 契約**：`wait_until` 用 truthy 判斷。要等「值變成特定內容」請用 `wait_for_change` 或自己包一層 lambda。

## 整合方式（建議 patch，**未套用**，由 BOB 決定）

`src/desktop_harness/helpers.py`（示意；此檔內容未在本次審閱片段中，行號與確切位置請依實際檔案調整）：

```python
# 1) import
from fmb_feature import dh_wait          # 或把 dh_wait.py 搬成 desktop_harness/wait.py

# 2) namespace() 末尾（daemon 會用同一份 namespace，因此 daemon 路徑自動受益）
def namespace():
    ...
    ns["wait_until"] = dh_wait.wait_until
    ns["wait_for"] = dh_wait.wait_for
    ns["wait_until_gone"] = dh_wait.wait_until_gone
    ns["wait_for_change"] = dh_wait.wait_for_change
    ns["poll_stable"] = dh_wait.wait_stable   # 刻意改名，避免覆蓋既有 helpers.wait_stable()
    ns["Deadline"] = dh_wait.Deadline
    return ns
```

`SKILL.md` 的「Meta」一行建議改成：

```text
- Meta: `wait`, `wait_stable`, `wait_for(...)`, `wait_for_change(...)` —
  動作後用它們等畫面到位，再呼叫 `verify(...)`
```

### 兩個要注意的整合細節

1. **不要覆蓋 `helpers.wait_stable`**：既有那個是固定 sleep、回 `None`；新的是輪詢、回 `WaitResult`。同名會讓既有腳本語意默默改變，所以建議以 `poll_stable` 曝光。
2. **一次 script 內完成輪詢**：`wait_until` 在 daemon 內執行時是同一個 warm process，輪詢本身幾乎零成本；千萬不要「每 poll 一次就跑一次 CLI」，那會被 socket round-trip 吃掉全部收益。

### 若要隨 wheel 出貨

`pyproject.toml` 目前只打包 `src/desktop_harness`。要讓這個模組進 wheel，需把它搬到 `src/desktop_harness/wait.py`（並同步上面的 import）。本 PR 依規則不動 `pyproject.toml`。

## 安全

- 只**觀察**，不新增任何鍵盤／滑鼠／螢幕操作路徑，因此 `safety.check_frontmost_allowed()` 等既有 gate 對被輪詢的 callable 完全照舊生效。
- 不讀寫檔案、不連網、不碰環境變數、不處理任何憑證或個資。
- 測試資料全是假值（`"A"`、`"hit"`、`{"pane": "General"}`）。

## 未完成 / 後續（各自都是獨立小 PR）

- `menu_click("File", "Save")` 的 AX 選單走訪（review #12）。
- clipboard get/set（review #12）。
- `wait_for_node(text, role=...)` 這種直接吃 `helpers.find` 簽章的包裝——本次刻意不猜 `find()` 的實際參數名，等 BOB 確認。
- AX snapshot TTL cache（review #9 的三～四次 walk）——與本模組互補，但屬不同關注點。

## 決策點（本 PR 採取的保守選擇）

1. **predicate 例外預設吞掉並重試**（`errors=(Exception,)`）：對 AX 讀取很合理，但可能把真正的 bug 延後。要嚴格時傳 `errors=()`；`last_error` 也會保留失敗軌跡。
2. **預設 `timeout=5.0`**：偏寬鬆、不會太快放棄；daemon 內熱路徑可傳 0.5～1.0，`interval` 可降到 0.02～0.05。
3. **成功判定用 truthiness**，不是「不等於 None」：少一個坑，但也意味著空 list／0 會被視為失敗；需要精確語意時用 `wait_for_change`。
4. **命名不叫 `wait_for_text`**：核心保持與 UI 無關（任何 callable 都能輪詢），文字／role 的便利包裝留給後續。

## 需要 BOB 決定的事

1. `helpers.namespace()` 要曝光哪些名字（是否接受 `poll_stable` 這個改名以保護既有 `wait_stable`）。
2. 檔案最終落點：留在 `fmb_feature/`（不進 wheel）或搬進 `src/desktop_harness/wait.py`（需改 `pyproject.toml` 與 import）。
3. `SKILL.md` 的「Meta」與「Verify, don't assume」段落是否同步加入 `wait_for` 的用法範例。
4. 是否要把 `verify()` 實作改成內部使用 `wait_for_change`，讓「點完就截圖」的競態一次解掉。
