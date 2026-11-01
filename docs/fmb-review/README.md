# desktop-harness 程式碼審查報告（fmb-review）

- **日期：** 2026-08（程式碼審查）
- **範圍：** 正確性、併發、錯誤處理、可讀性、可測試性、相依風險
- **性質：** 僅新增審查文件，**未修改任何原始碼**。所有修法均為提案，需另行開分支實作。
- **repo：** YourheroBOB/desktop-harness @ v0.4.2（以審視用工作樹快照為準）

---

## 1. 範圍與限制（先講清楚）

### 1.1 已完整審查（有完整檔案內容可逐行審查）

| 檔案 | 類型 | 產出 finding 前綴 |
|------|------|-------------------|
| `scripts/voice_session.py` | 實驗性語音 session 迴圈 | VS-* |
| `scripts/observe-demo.sh` | 密集截圖觀察腳本 | OBS-* |
| `install.sh` | 一鍵安裝 | INS-* |
| `desktop-harness` | dev launcher（shell） | LAU-* |
| `pyproject.toml` | 打包與相依宣告 | PKG-* |
| `.gitignore` | repo 衛生 | GIT-* |
| `src/desktop_harness/demo.py` | 可見煙霧測試 | DEMO-* |
| `README.md`、`RELEASE.md`、`SKILL.md`、`VOICE.md`、`docs/*`、ADR | 一致性／可維護性 | DOC-* |
| 跨模組架構觀察（基於 ADR 與文件推論） | 架構風險 | ARCH-* |

### 1.2 未在審查視野內（工作樹未提供內容，**不假裝審過**）

`src/desktop_harness/helpers.py`、`ax.py`、`input.py`、`run.py`、`presence.py`、`daemon.py`、`windows.py`、`capture.py`、`safety.py`、`admin.py`、`selftest.py`、`voice_tools.py`、`agent-workspace/agent_helpers.py`、`docs/PRE-RELEASE-REVIEW.md`、`docs/fmb-security/*`。

這些模組的已知問題請一併參閱：

- `docs/fmb-perf/findings-daemon.md`（DAEMON-1..7，含 **P0**：單執行緒 accept loop、未捕捉 socket 例外）
- `docs/fmb-perf/findings-perception.md`（PERC-1..5）
- `docs/fmb-perf/findings-timeouts-recovery.md`（TR-1..6）
- `docs/fmb-perf/findings-observability.md`（OBS-1..4）
- `docs/fmb/ROADMAP.md` / `ROADMAP-ZH-TW.md`

本報告聚焦上述文件**未覆蓋**的腳本／打包／安裝／文件層面，並在必要處交叉引用。

### 1.3 行號錨點說明

所有 `檔案:行號` 基於 v0.4.2 快照。實作 PR 時請以**函式／符號名稱**為準確認錨點，例如：

```bash
grep -n "dry_run=False" scripts/voice_session.py
grep -n "typing anyway" src/desktop_harness/demo.py
```

---

## 2. 優先級定義（與 fmb-perf 一致）

| 級別 | 定義 |
|------|------|
| **P0** | 主要功能整體失效、掛死、或單一事件可讓常駐进程崩潰 |
| **P1** | 正確性／隱私／安全明顯缺陷，或明顯的可靠性缺口 |
| **P2** | 打磨項：可觀測性、邊界情況、測試隔離、文件一致性、相依風險 |

**本次視野內未發現 P0**（daemon 的 P0 位於未提供的 `daemon.py`，見 fmb-perf DAEMON-1/2）。

---

## 3. 發現總表

### 3.1 語音 session（`scripts/voice_session.py`）

| ID | 嚴重度 | 類別 | 標題 | 詳情 |
|----|--------|------|------|------|
| VS-1 | **P1** | 正確性／安全語意 | `--dry-run` 實際會執行真實（唯讀）GUI 呼叫，與 help 文字宣稱不符 | [findings-voice-session.md](./findings-voice-session.md) |
| VS-2 | **P1** | 隱私 | 工具參數與結果原樣印出，`type_text` 等內容會進終端機 scrollback／log | 同上 |
| VS-3 | **P1** | 併發 | `execute()` 同步阻塞 asyncio event loop，長動作卡死 WS／音訊 | 同上 |
| VS-4 | **P1** | 逾時 | `websockets.connect` 無 `open_timeout`，事件迴圈無 idle timeout → 無限掛死 | 同上 |
| VS-5 | P2 | 錯誤處理 | 迴圈內未捕捉 `json.loads`／`ConnectionClosed`／工具例外 → raw traceback、無 exit code 語意 | 同上 |
| VS-6 | P2 | 併發／成本 | `response.done` + `pending_calls` 自動續 turn 無上限 → 可能無限燒 API 額度 | 同上 |
| VS-7 | P2 | 正確性（待確認） | `arguments` 以 JSON 字串傳給 `execute()`，簽名契約需對齊 | 同上 |
| VS-8 | P2 | 可用性 | 無 `--text` 時列 server_vad 但無麥克風串流，行程只會掛住 | 同上 |
| VS-9 | P2 | 相依風險 | `GROK_VOICE_MODEL` 未驗證直接插入 URL query | 同上 |
| VS-10 | P2 | 可測試性 | `execute`／ws 工廠未注入，難以離線單測 | 同上 |

### 3.2 安裝與腳本

| ID | 嚴重度 | 類別 | 標題 | 詳情 |
|----|--------|------|------|------|
| INS-1 | P2 | 破壞性 | `install.sh` 無條件覆寫 `~/.local/bin/desktop-harness` | [findings-scripts-install.md](./findings-scripts-install.md) |
| INS-2 | P2 | 錯誤恢復 | SKILL.md 直接重導向寫入，失敗會留半份檔案給 Grok | 同上 |
| INS-3 | P2 | 可攜性 | 無 macOS / python3>=3.10 preflight，Linux 上失敗訊息難懂 | 同上 |
| INS-4 | P2 | 可測試性 | `--doctor \|\| true` 使 install.sh 永遠 exit 0，無法作為 CI gate | 同上 |
| INS-5 | P2 | 可攜性 | shim 內建絕對 `$ROOT`，clone 搬移後靜默失效 | 同上 |
| INS-6 | P2 | 冪等性 | 重跑安裝沿用可能損壞的 `.venv` | 同上 |
| INS-7 | P2 | 相依風險 | pip 安裝未鎖版本下限 | 同上 |
| INS-8 | P2 | 錯誤處理 | venv／pip 失敗訊息未包裝 | 同上 |
| OBS-1 | P2 | 測試隔離 | 預設輸出固定 `/tmp/dh-observe`，併發執行互撞 | [findings-scripts-install.md](./findings-scripts-install.md) |
| OBS-2 | P2 | 錯誤處理 | `screencapture … \|\| true` 靜默吞錯，零影格只出現在最後一行 | 同上 |
| OBS-3 | **P1** | 安全／正確性 | 固定座標 `click(520,420)` 會點到開發者當下畫面的任何東西 | 同上 |
| OBS-4 | P2 | 錯誤處理 | `source .venv/bin/activate 2>/dev/null \|\| true` 靜默退回系統版 CLI | 同上 |
| OBS-5 | P2 | 可讀性 | `rm -f "$OUT"/*.png` 對空字串參數防護不足 | 同上 |
| LAU-1 | P2 | 正確性 | launcher 用 `dirname "$0"`，透過 symlink 呼叫時 `PYTHONPATH` 錯誤 | 同上 |
| LAU-2 | P2 | 錯誤處理 | `.venv/bin/python` 存在但損壞時只拿到晦澀 exec 錯誤 | 同上 |
| LAU-3 | P2 | 可讀性 | 未檢查 python3 >= 3.10 | 同上 |

### 3.3 打包與 repo 衛生

| ID | 嚴重度 | 類別 | 標題 | 詳情 |
|----|--------|------|------|------|
| PKG-1 | P2 | 相依風險 | 三個 pyobjc 相依完全未鎖下限 | [findings-packaging-hygiene.md](./findings-packaging-hygiene.md) |
| PKG-2 | P2 | 打包 | 無 license 元資料（有 `LICENSE` 檔但 wheel 不帶） | 同上 |
| PKG-3 | P2 | 打包 | 語音 extras（websockets/sounddevice/numpy）未宣告為 optional-dependencies | 同上 |
| PKG-4 | P2 | 可維護性 | 根 `SKILL.md` 與 `src/desktop_harness/data/SKILL.md` 兩份真相，可能漂移 | 同上 |
| PKG-5 | P2 | 可測試性 | 無 pytest 設定（roadmap 第 1 項要場景化測試，需要地基） | 同上 |
| GIT-1 | P2 | 安全 | `.gitignore` 無 `.env`／`*.pem`／`*.key`／token 模式 | 同上 |
| GIT-2 | P2 | 可維護性 | `*.png` 全 repo 忽略，未來文件圖片會被誤擋 | 同上 |

### 3.4 文件一致性

| ID | 嚴重度 | 標題 | 詳情 |
|----|--------|------|------|
| DOC-1 | P2 | README／RELEASE 指向 `xfreeze2/desktop-harness`，與本 repo `YourheroBOB/desktop-harness` 不一致 | [findings-packaging-hygiene.md](./findings-packaging-hygiene.md) |
| DOC-2 | P2 | 文件以 `PRE-RELEASE-REVIEW #N` 編號互相引用，編號一改全斷 | 同上 |
| DOC-3 | P2 | `ROADMAP.md` 與 `ROADMAP-ZH-TW.md` 同一批 10 項但排序不同 | 同上 |
| DOC-4 | P2 | `voice_hotkey_readme.md` 鼓勵把 key 寫在命令行（進 shell history） | 同上 |

### 3.5 執行期煙霧測試（`src/desktop_harness/demo.py`）

| ID | 嚴重度 | 標題 | 詳情 |
|----|--------|------|------|
| DEMO-1 | **P1** | 找不到 TextEdit 視窗時仍 `type_text` → 按鍵可能打進任何前景 app | [findings-demo-runtime.md](./findings-demo-runtime.md) |
| DEMO-2 | P2 | 無條件 `cmd+n` 可能撞上「未儲存變更」對話框，後續動作全失準 | 同上 |
| DEMO-3 | P2 | `wins[0]` 多視窗時任選一個 | 同上 |
| DEMO-4 | P2 | 固定 `sleep` 時序競爭（交叉引用 TR-5／PRE-RELEASE #13） | 同上 |
| DEMO-5 | P2 | 永遠 `return 0`，失敗無訊號 | 同上 |
| DEMO-6 | P2 | 變更畫面後未依 ADR-0009 呼叫 `verify()` | 同上 |
| DEMO-7 | P2 | `open_app` 例外直接 traceback，無操作提示 | 同上 |
| DEMO-8 | P2 | 視窗 bounds 原點與輸入座標系一致性未驗證（待確認） | 同上 |

### 3.6 跨模組架構（基於 ADR／文件推論，實作模組未在視野內）

| ID | 嚴重度 | 標題 | 詳情 |
|----|--------|------|------|
| ARCH-1 | P0（引用） | daemon 單執行緒 accept loop + 無連線逾時（ADR-0006 自述） | [findings-demo-runtime.md](./findings-demo-runtime.md) |
| ARCH-2 | P2 | 任意 exec 表面（ADR-0003）只包少數 helper，建議補「腳本指紋」審計 | 同上 |
| ARCH-3 | P2 | presence main-thread 約束（ADR-0006）已固化，列為未來 PR 審查清單 | 同上 |

---

## 4. 前十大修補建議（摘要版）

完整版含程式片段與排程：[top10-remediation.md](./top10-remediation.md)。

| # | 項目 | 涵蓋 finding | 工作量 | 一句話價值 |
|---|------|--------------|--------|-----------|
| 1 | `voice_session.py` dry-run 語意修正 + 參數遮標 | VS-1, VS-2 | S | 防止「以為在模擬卻動了真 GUI」與內容外洩 |
| 2 | `voice_session.py` 逾時／錯誤處理／執行緒卸載 | VS-3, VS-4, VS-5 | S–M | 消除無限掛死與音訊卡死 |
| 3 | `demo.py` 安全護欄 + `verify()` + exit code | DEMO-1, 5, 6 | S | 不把按鍵打進錯誤 app；煙霧測試可自動化 |
| 4 | voice turn 上限 + 依賴注入 | VS-6, VS-10 | S | 防止 API 額度無限燃燒；可離測 |
| 5 | `install.sh` 強化（preflight／原子寫入／shim 保護／strict） | INS-1..8 | S–M | 不再靜默破壞使用者既有檔案 |
| 6 | `observe-demo.sh` 穩健化 | OBS-1..5 | S | 無權限時早失敗；不誤點他人畫面 |
| 7 | 打包衛生（相依下限／extras／license／pytest） | PKG-1..5 | S | 可重現建置 |
| 8 | `.gitignore` 機密模式 | GIT-1 | S（0.5h） | 避免金鑰誤提交 |
| 9 | 文件一致性（repo URL／roadmap 對齊／穩定 ID） | DOC-1..4 | S | 降低新人成本與文件腐敗 |
| 10 | 座標與 `execute` 契約驗證測試 | DEMO-8, VS-7 | M | 把兩個「待確認」變成有測試錨定的契約 |

---

## 5. 檔案索引

| 檔案 | 內容 |
|------|------|
| [findings-voice-session.md](./findings-voice-session.md) | `scripts/voice_session.py` 逐項審查（VS-1..10） |
| [findings-scripts-install.md](./findings-scripts-install.md) | `install.sh`／`observe-demo.sh`／launcher（INS/OBS/LAU） |
| [findings-packaging-hygiene.md](./findings-packaging-hygiene.md) | `pyproject.toml`／`.gitignore`／文件一致性（PKG/GIT/DOC） |
| [findings-demo-runtime.md](./findings-demo-runtime.md) | `demo.py`（DEMO）+ 未審模組檢查清單 + 架構觀察（ARCH） |
| [top10-remediation.md](./top10-remediation.md) | 前十大修補建議、程式片段、工作量、排程 |
| [verification-plan.md](./verification-plan.md) | 不連正式服務、不寫 repo 外的驗證方案 |

---

## 6. 驗證原則（所有 finding 共通）

1. **不連線任何網路正式服務**：語音驗證一律 mock 本地 WS server 或 `--dry-run`；金鑰一律 `FAKE_VALUE_FOR_TEST`。
2. **不讀寫 repo 外路徑**（`tempfile`／`tmp_path` 沙箱除外）。
3. **不改使用者目前正在跑的 daemon／滑鼠狀態**：GUI 相關測試用注入式 fake helpers。
4. 只新增文件；所有修法為提案，由 BOB 決定是否開實作分支。

---

## 7. 決策點（保守預設，詳見 top10 與 SUMMARY）

- D1：`--dry-run` 採最保守語意——**永不執行真實 GUI**（唯讀工具也改走 dry-run 或明確 allowlist）。
- D2：voice 自動續 turn 預設上限 8 次。
- D3：pyobjc 相依下限暫記 `>=10.0`，實作當天以 venv 實際版本校準。
- D4：repo URL 混亂（`xfreeze2` vs `YourheroBOB`）只回報不改，由 BOB 指定 canonical upstream。
- D5：SKILL.md 雙份真相暫以「根目錄為 source of truth」為預設，實作再確認。
- D6：本審查不猜測未提供檔案的內容；核心模組問題一律引用 fmb-perf／PRE-RELEASE，不重複發明。
