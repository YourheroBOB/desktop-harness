# ADR-0001：AX 優先的分層感知

**狀態：** 接受中（v0.1 起即為核心原則）  
**相關模組：** `ax.py`、`capture.py`、`helpers.py`

## 背景

桌上型電腦控制的常見做法是「截圖 → 視覺模型 → 猜座標 → 點擊 → 重複」。這條路能力強但**慢且貴**：每一步都要付一次視覺推論的延遲與成本，而且座標是猜出來的。

macOS 原生就對輔助功能暴露完整的 **Accessibility（AX）tree**：按鈕、標籤、欄位都是以結構化文字呈現，讀取只要數十毫秒，且元素自帶可執行的動作（`AXPress`、設定 value）。coding agent 擅長 shell 與結構化資料，不擅長猜像素。

## 決策

採用**四層感知階梯**，由便宜到昂貴，且必須由上往下嘗試：

| 層 | 手段 | 成本 |
|----|------|------|
| 1 | Shell / API（能用非 GUI 就不用 GUI） | ~0 |
| 2 | AX tree（`ax_snapshot` / `labels` / `find`）——**主要眼睛** | 數十 ms |
| 3 | 視窗截圖（`screenshot`）——AX 空乏時的 fallback | 50–150 ms |
| 4 | OCR / 視覺——最後手段 | 昂貴 |

配套的動作原則：**元素動作優先於座標**。`click_text` 先找 AX 元素並偏好 `AXPress`；只有不存在 AX 動作時才退回座標點擊。截圖也偏好 **window 範圍**而非全螢幕。

## 取捨

- **放棄了**「一套截圖 pipeline 打通所有 app」的通用性：Electron、canvas、遊戲類 app 的 AX 稀疏，必須退到截圖／視覺層，體驗會明顯變慢。這被明確列為 known limit 而非 bug。
- **放棄了**像素級的普遍性 換取 原生 app 上的速度與確定性：AX 給的是「`"Save" 按鈕`」這種確定事實，而非「看起來像 Save 的區塊」。
- tree 必須保持**精簡**（互動節點優先、有 `max_nodes` 上限），否則 agent 的 context 會被 AX 傾印淹沒——精簡是階梯能成立的必要條件。

## 後果

- 正面：多數日常任務（System Settings、TextEdit、Safari chrome、Finder）不需要視覺模型，速度快、token 省、動作確定。
- 負面：任何「AX 空乏」的 app 都成為二級公民；文件必須誠實標註此限制（見 `RELEASE.md` known limits）。
- 衍生決策：`find` 的配對分數、`click_text(exact=True)`、`media_transport` 等都是為了讓第 2 層更可靠而生的（見 ADR-0007）。
- 「絕不預設 vision loop」成為 skill 中的**強制**規則，而非建議。
