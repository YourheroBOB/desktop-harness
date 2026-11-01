# 新進開發者上手指南（補充篇）：模組地圖、資料流、常見修改路徑與陷阱

> 本篇是 [ONBOARDING.md](./ONBOARDING.md) 的**補充**，聚焦「要動 code 時從哪下手、會踩什麼坑」。
> 環境建置、安裝、第一次執行請以 ONBOARDING.md 與根目錄 `install.md`／`README.md` 為準；
> 設計理念與完整架構說明見 `DESIGN.md` 與 `docs/fmb/ARCHITECTURE*.md`。
> 任何「為什麼這樣寫」的問題，先查 [ADR 索引](./README.md)——大多數決策都有成文答案。

---

## 1. 五分鐘模組地圖

| 模組 | 職責 | 動手前要知道 |
|------|------|--------------|
| `src/desktop_harness/run.py` | CLI 入口：子命令解析、daemon 路由（`DH_NO_DAEMON`、0.4s ping） | 新增子命令要同步 `docs/fmb-api/cli.md` |
| `src/desktop_harness/helpers.py` | 公開 API 表層，組出腳本命名空間（併入 `agent_helpers.py`） | 任務特定包裝放 agent_helpers，別膨脹核心（ADR-0014） |
| `src/desktop_harness/windows.py` | `list_apps`／`list_windows`／`frontmost_app`／`find_app`／`activate` | 找 app 是精確→前綴→最短子字串→bundle id 的排序學 |
| `src/desktop_harness/ax.py` | AX 樹走訪、`ax_snapshot`／`find`／`labels`、`AXPress`、`frame_on_screen` | 這是主要「眼睛」；樹要精簡，別整棵倒出（ADR-0001） |
| `src/desktop_harness/capture.py` | 視窗／螢幕 PNG（回落路徑） | 截圖前跑敏感 app 檢查；暫存檔清理是已知缺口（PERC-3） |
| `src/desktop_harness/input.py` | CGEvent／CGWarp 真實滑鼠鍵盤 | 座標點擊要目標在前景；presence 光環要同步 |
| `src/desktop_harness/safety.py` | 敏感 app 閘門、前景檢查、audit log | 截圖敏感前景同於點擊（ADR-0008）；audit 不記內容（ADR-0012） |
| `src/desktop_harness/daemon.py` | NDJSON over Unix socket、0600、token、PID 單例 | 是「本機特權 exec 端點」；單執行緒 accept 迴圈有已知限制（DAEMON-1/2） |
| `src/desktop_harness/presence.py` | 游標光環＋「hands off」橫幅、`keep_alive()` | AppKit 只能主執行緒（ADR-0006）；背景執行緒會 SIGABRT |
| `src/desktop_harness/admin.py` | `--doctor` 權限健檢 | 授權後 Screen Recording 要重啟 host app 才生效 |
| `src/desktop_harness/selftest.py` | 非破壞自測 | daemon 往返會停掉使用者已在跑的 daemon（TR-6），跑之前先 `daemon status` |
| `src/desktop_harness/demo.py` | 可見煙霧測試 | 找不到目標視窗必須 abort，不可把按鍵打進未知 app（DEMO-1） |
| `voice_tools.py` + `scripts/voice_session.py` | 實驗性語音控制 | optional、需自備 key、不進核心依賴（ADR-0011） |

---

## 2. 一次呼叫的資料流

```
agent
  │  desktop-harness <<'PY' … PY
  ▼
run.main ── 讀 stdin 腳本
  ├─ DH_NO_DAEMON=1 ─────────────────► _exec_local（本機行程）
  └─ daemon.is_running()（socket ping，timeout 0.4s）
        ├─ up   → exec_via_daemon（驗 token → 常駐行程 exec）
        └─ down → _exec_local
  ▼
namespace() = helpers + agent_helpers
  ├─ windows.py（列舉／尋找／啟用）──┐
  ├─ ax.py（快照／尋找／按下）       ├─ safety.py（敏感閘門 + audit.jsonl）
  ├─ capture.py（PNG 回落）         ─┘
  ├─ input.py（CGEvent 真實手）
  └─ presence.py（光環／橫幅，僅主執行緒）
  ▼
{ok, stdout, stderr} 回給 agent
```

要記住的三個稽核點：

1. **路由點**：daemon 活著就走 socket（快），否則本機重跑（慢但乾淨）。
2. **安全點**：`safety.py` 在開啟／前景變更／截圖前把關，通過後寫 audit（只記行動，不記內容）。
3. **驗證點**：任何改變畫面的動作，回程要用 `verify()` 讀回畫面確認（ADR-0009）——AX 呼叫沒拋錯 ≠ 畫面如預期。

---

## 3. 常見修改路徑

| 我想… | 主要檔案 | 動之前必做 | 參考 |
|------|----------|------------|------|
| 新增 agent 可呼叫的通用 helper | `helpers.py`（含命名空間匯出） | 過安全閘門、audit 只記中繼資料、更新 `docs/fmb-api/` 與 `SKILL.md`（根目錄與 `src/desktop_harness/data/` 兩份） | ADR-0003、ADR-0012 |
| 新增任務特定包裝 | `agent-workspace/agent_helpers.py` | 不動核心；注意它等於可信程式碼 | ADR-0014 |
| 改 `find`／`labels`／快照行為 | `ax.py` | 維持 compact tree 契約；輪詢條件等待優於固定 sleep | ADR-0001、ROADMAP 第 1/3 項 |
| 改滑鼠／鍵盤手感 | `input.py` | presence 光環同步、`DH_MOUSE_INSTANT` 語意不變 | ADR-0005 |
| 改安全政策／敏感名單 | `safety.py` | 同步 `SECURITY.md` 與 ADR-0008；名稱子字串過寬是已知問題 | ADR-0008、ROADMAP 第 6/9 項 |
| 改 daemon | `daemon.py` | 維持 NDJSON 相容、0600、單實例；先讀 `docs/fmb-perf/findings-daemon.md` | ADR-0004 |
| 改 presence | `presence.py` | 只走主執行緒；observe loop 密集截圖，含焦點轉移與空轉 | ADR-0006、`docs/OBSERVE-LOOP.md` |
| 新增 CLI 子命令 | `run.py` | 更新 `docs/fmb-api/cli.md` | ADR-0002 |
| 加依賴／改打包 | `pyproject.toml`、`install.sh`、`desktop-harness` launcher | 版本下限、不把 voice 依賴進核心、`SKILL.md` 雙份真相 | ADR-0011、PKG-1..5 |
| 動語音實驗 | `scripts/voice_session.py`、`voice_tools.py` | 維持 optional；`--dry-run` 不得碰真實 GUI；不寫 key | ADR-0011、VS-1/VS-2 |
| 寫文件 | `docs/fmb*/`、根目錄 md | 繁體中文、不連線、不寫任何密鑰或個資 | ADR-0015 |

---

## 4. 陷阱清單

1. **AppKit 只能主執行緒**：背景執行緒碰 window 方法會直接 SIGABRT（無 Python 例外、救不回來）。等待要用 `keep_alive()` 分片 pump，不要開 thread。（ADR-0006）
2. **AX 成功 ≠ 畫面成功**：動作沒拋錯只代表呼叫成功。改畫面的路徑結尾一定 `verify()` 並讀回傳的截圖。（ADR-0009）
3. **媒體只 look-once／act-once**：先讀 `media_transport()`，已在播放就停手；絕不連按 Space（會 toggle 暫停），絕不寬比對 `"Play"`。（ADR-0007、`docs/POSTMORTEM-media-play.md`）
4. **固定 sleep 會 race**：慢機來不及渲染、快機白等。改為有逾時的條件輪詢。（TR-5、DEMO-4、ROADMAP 第 1 項）
5. **截圖敏感前景 = 洩漏**：前景是密碼管理器類 app 時，截圖與點擊同級阻擋；新增 capture 路徑不可繞過 `check_frontmost_allowed()`。（ADR-0008）
6. **audit 不記內容**：新 helper 的審計只記動作與長度，不記打字、剪貼簿、訊息內文。（ADR-0012）
7. **daemon 是特權端點**：socket／token 0600、PID 單例、stale socket 要清；單執行緒 accept 迴圈與未捕捉例外的 P0 問題在動手前先讀 findings。（ADR-0004、DAEMON-1..7）
8. **任意 exec 的爆炸半徑**：腳本可 `import subprocess` 繞過 `DH_*` 閘門——這是有意的彈性，文件不可宣稱 runtime 能擋危險意圖。（ADR-0003、ADR-0010）
9. **測試紀律**：不連線正式服務（voice 用 mock／`--dry-run`）；不讀寫 repo 外路徑（用 `tmp_path`／tempfile 與 `DH_SOCKET`／`DH_TOKEN_PATH`／`DH_AUDIT_LOG`）；不停使用者正在跑的 daemon；假憑證一律 `FAKE_VALUE_FOR_TEST`。
10. **presence 的驗證方式**：一張靜態截圖證明不了什麼。必須 demo 到「點擊切到別的 app 後空轉數秒」，並用多幀確認光環／橫幅還在——這個 bug 真的 shipped 過一次。（`docs/OBSERVE-LOOP.md`、`SKILL.md`）
11. **文件漂移**：README／install／RELEASE 的 clone URL 指向 `xfreeze2`，與本 repo `YourheroBOB` 不一致（DOC-1，待 BOB 定 canonical upstream）；文件間以 review 編號互引容易斷（DOC-2）——引用檔案／章節，別引用編號。
12. **SKILL.md 兩份真相**：根目錄與 `src/desktop_harness/data/SKILL.md`（wheel force-include）需一致；改技能內容記得兩處或依 PKG-4 的決策收斂。
13. **審查文件只提案不改碼**：`docs/fmb-perf/`、`docs/fmb-review/` 是報告，修法都要另開分支實作——讀的時候不要以為已經修了。

---

## 5. 送出 PR 前的檢查清單

- [ ] 只動必要檔案；沒有碰 `.github/workflows`、secrets／憑證設定、其他人的 daemon。
- [ ] 沒有任何 token、金鑰、密碼、客戶個資、LINE 訊息內文或案件當事人資料；測試假值用 `FAKE_VALUE_FOR_TEST`。
- [ ] 改變畫面的路徑有 `verify()`；媒體路徑 look-once／act-once。
- [ ] 新 helper 有安全閘門思考 + audit 只記中繼資料。
- [ ] 測試用 `tmp_path`／`DH_*` 覆寫，不連網正式服務。
- [ ] 文件同步：`docs/fmb-api/`、`SKILL.md`（兩處）、若為決策變更另開 ADR。
- [ ] presence 改動附多幀截圖證據（含焦點轉移與空轉）。
- [ ] 若跨越 [ADR-0015](./ADR-0015-explicit-non-goals.md) 的非目標，先在 PR 裡講清楚，不要偷渡。
