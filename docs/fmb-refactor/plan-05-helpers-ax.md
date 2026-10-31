# 批次 5（高風險）：`helpers.py` / `ax.py` 結構整頓

- **範圍：** `src/desktop_harness/helpers.py`、`src/desktop_harness/ax.py`
- **風險：** **高** — 此二檔為產品核心路徑（`click_text`、`find`、`media_transport`），且**本規劃未直接檢視其原始碼**
- **對應 findings：** D8、L4、L5、N6 + review #6/#8/#9/#14/#15
- **行為變更：** 修的是 review 已列明的 **bug**（pid crash、media 死分支）；重複 walk 的削減不改對外回傳

## 0. 硬性前置（不可跳過）

> 本批所有發現均引自 `docs/PRE-RELEASE-REVIEW.md` 的程式碼摘錄（2026-08-10 的 review 約當 v0.3 前後）與 `docs/fmb-perf/`。v0.4.2 期間已有修正落地（例如截圖唯一檔名 #17、doctor #21 已修），**部分引用項可能已不存在**。動手前必須：
>
> 1. 逐項重讀 `helpers.py`／`ax.py` 最新原始碼，把下表標記為「已修／仍在」。
> 2. 已修的項目直接從本批移除，不為了重構而重構。
> 3. 本批拆成多個小 PR（每項一個），任何一項沒有特徵測試就不動。

## 1. 引用的問題清單

| ID | 來源 | 問題 | 現況假設 |
|----|------|------|----------|
| P1 | review #6 | `click_text` 的 pid 路徑：`find_app` 收到 `int` 會在 `.strip().lower()` 丟 `AttributeError` | 待確認 |
| P2 | review #8 | `media_transport` 的 `has_play` 只在 exact `"play"` 成立，外層條件允許 `"play "` 開頭但內層死分支 | 待確認（ADR-0007 說 selftest 有 `play == transport_play` 斷言，可能已部分修） |
| P3 | review #9 | `ensure_media_playing` 一次動作 3–4 次完整 AX walk；`click_text` miss 後另取樣 walk | 待確認 |
| P4 | review #15 | `ax.walk` 互動過濾巢狀分支難推理，幾乎全 `keep=True` | 待確認 |
| P5 | review #14 | `ax._ax_point` 魔術整數 `1`/`2` | 待確認 |

## 2. 需先補的測試（動手前，全部離線）

pyobjc 相關以 monkeypatch／假 AX element dictionary 釘行為，不依賴真實 UI：

1. **`find` 配分特徵測試**（ADR-0007 的規則化）：exact `"Play"` 必須贏過 `"Play all"`／`"Playing from"`；`exact=True` 只配完全相等；無命中時的回傳形狀。
2. **`media_transport` 狀態機特徵測試**：造假節點清單分別含 transport Pause／row Play／只有 `"Play <track>"`，斷言 `{state, transport_play, row_play, play}` 的每種組合（P2 的修法必須先把這些現況釘住，才知道哪些是 bug 哪些是設計）。
3. **`click_text` pid 路徑**：`app=<某 pid>` 時的 activate 名稱解析（P1）— 修前以 `find_app(int)` 丟 `AttributeError` 的現況為紅燈測試。
4. **walk 計數測試**：monkeypatch AX 走訪計數器，斷言 `ensure_media_playing` 在「已播放（noop）」與「需按 Play」兩情境下的 walk 次數（P3 的基準線）。
5. **`frame_on_screen` 純函式測試**（已有 selftest 覆蓋，搬進單測層）。

## 3. 重構項目與前後對照（提案，依 §0 確認後才實作）

### 3.1 P1：pid 解析抽出（L4）

重構前（review 摘錄）：

```python
activate(str(app) if not isinstance(app, int) else (
    find_app(app) or {}).get("name", "Finder"))
```

重構後（提案）：

```python
def _target_app_name(app: str | int) -> str | None:
    """Resolve an app argument (display name or pid) to a display name.

    pid → look up via list_apps(); unknown pid → None (caller decides
    whether falling back to Finder is still the right behavior).
    """
    if isinstance(app, int):
        for a in windows.list_apps():
            if a.get("pid") == app:
                return a.get("name")
        return None
    return str(app)
```

> 注意：原碼在找不到名稱時 fallback `"Finder"` — 這是可疑行為（目標 pid 不存在卻去啟用 Finder）。修法保守起見**保留** fallback 但改為顯式 `if name is None: name = "Finder"` 並加註解，避免重構順手改變行為；要不要移除 fallback 列為 BOB 決策點。

### 3.2 P2：media 死分支顯性化

重構後（提案，語意：transport 級與 row 級分開為兩個旗標）：

```python
low = (label or "").strip().lower()
is_transport = <該按鈕屬於 transport 列的判斷，依現行實作>
if low == "play":
    if is_transport:
        transport_play = True
    else:
        row_play = True
# "play <track>" 開頭的 row 級項目 → 只設 row_play，不算 transport_play
# （與 ADR-0007 的 play == transport_play 斷言一致）
```

實際形狀**以 §2.2 特徵測試釘住的現況為準**；原則是：外層條件與內層賦值不再有不一致的可能性 — 每個被外層放行的 case 都明確落到一個旗標。

### 3.3 P3：重複 walk 削減（D8）

分兩步（各自可獨立驗收）：

1. **`click_text` miss 的取樣重用**：`find()` 內部已走訪過的節點（或其前 N 筆）直接作為 miss 時的樣本輸出，不再另跑一次 `ax_snapshot(max_nodes=40)`。以 §2.4 的 walk 計數測試斷言 miss 路徑 walk 次數 -1。
2. **daemon 內快照快取**：ROADMAP 第 5 項（TTL 150ms、key 含 `(pid, interactive_only, max_nodes)`、只存在 daemon 行程內）。此步接近新功能，**建議獨立於本批**，待 ROADMAP 排期；本批只做第 1 步。

### 3.4 P4：`ax.walk` 過濾簡化

依 review #15 的建議方向：改寫為「互動角色保留 + 有標籤的葉節點保留 + 容器一律下探」三條明確規則，以 §2.1 的 `find` 配分測試 + 一份固定假樹 fixture 的快照測試保證輸出節點集合不變（若現況過濾確實「幾乎全 keep」，快照測試會先把現況釘住，再以最小 diff 簡化）。

### 3.5 P5：`kAXValue` 常數

```python
# 重構前（review 摘錄）
… 1 …   # CGPoint
… 2 …   # CGSize
# 重構後
from ApplicationServices import kAXValueCGPointType, kAXValueCGSizeType
```

## 4. 驗證方式（每小項獨立驗收）

1. §2 特徵測試全綠（紅轉綠的項目 = bug 修復項）。
2. `desktop-harness selftest` 全 PASS（selftest 已含 media 狀態機與 find_app 排序斷言）。
3. `desktop-harness demo` 人眼煙霧。
4. 媒體實機驗證（若有播放器）：`media_transport()` 兩次讀取一致、`ensure_media_playing` noop 於播放中。
5. 每小項一 PR；P3 第 2 步（daemon 快取）不在本批。

## 5. 風險與回滾

- **這是全計畫風險最高的一批**：核心路徑 + 原始碼未直接檢視 + 部分引用項可能已修。§0 的「先重讀、先釘測試」是硬性閘門。
- `find` 配分與 media 狀態機是事故換來的行為（ADR-0007）— 任何改動都必須先有把**現況**釘死的測試，紅燈才代表真 bug。
- 回滾：每小項獨立 PR，逐一 revert 互不影響。
- **明確不做**：`wait_stable` 預設值縮短、`type_text` 延遲、clipboard paste（皆為 ROADMAP 功能/效能項）；`check_helper_allowed` 接線（屬 ROADMAP #6）。
