# desktop-harness 新進開發者上手指南

本指南基於 repo 現有文件與程式碼整理，目標：**一小時內知道程式碼長在哪、資料怎麼流、常見修改怎麼做、哪裡會踩雷**。架構決策的「為什麼」請搭配 [ADR 索引](./README.md)。

> 註：`ax.py`、`helpers.py`、`input.py`、`presence.py`、`run.py` 的細節部分由 `DESIGN.md`、`SKILL.md`、`docs/PRE-RELEASE-REVIEW.md` 與其他模組的呼叫關係推得；動手前請以實際程式碼為準。

## 1. 這是什麼

一句話：**macOS 上 AX 優先的桌面控制 CLI**，讓 coding agent（主要為 Grok Build）能用 shell 控制 real Mac：開 app、讀 UI、動滑鼠、點擊、打字。真實 HID、真實游標、無沙箱。

核心原則（不可協商，見 ADR-0001）：

1. Shell 優先於 GUI
2. AX 優先於像素
3. 視窗優先於全螢幕
4. 精簡 tree
5. 元素動作優先於座標
6. 預設不用 vision loop
7. 外送/破壞性動作前需 consent

## 2. 模組地圖

```
agent（Grok Build / 任何 shell agent）
  │  desktop-harness <<'PY' …
  ▼
run.py            CLI 進入點：解析子命令（demo/selftest/skill/daemon/--doctor）
  │               與 stdin script；決定走 daemon 或 in-process
  ▼
helpers.py        ★ 公開 API 面（public surface）——所有 helper 的聚集點
  ├── windows.py  app/視窗探索（NSWorkspace + CGWindowList）、activate、find_app
  ├── ax.py       ★ 主要眼睛：AX tree 走訪、find（配分）、AXPress、set value
  ├── capture.py  fallback 眼睛：視窗/全螢幕 PNG（CGWindowListCreateImage）
  ├── input.py    手：CGWarp + CGEvent 點擊/拖曳/滾動/鍵盤
  ├── presence.py 單一游標 + halo/pill 的視覺提示（AppKit，main-thread！）
  └── safety.py   敏感 app gate + 審計日誌（被上面四個呼叫）
daemon.py         warm daemon：NDJSON over Unix socket + token 認證（exec 語意）
selftest.py       非破壞性自測（含 daemon 往返、TextEdit 打字）
admin.py          --doctor：pyobjc / Accessibility / Screen Recording / AX 檢查
demo.py           可見冒煙測試（真的會動你的滑鼠、開 TextEdit）
voice_tools.py    （實驗性）Grok Voice 的 tool schema + 本地 executor
```

外圍：

| 檔案 | 角色 |
|------|------|
| `SKILL.md` + `src/desktop_harness/data/SKILL.md` | 教 agent 何時/如何用 CLI。**兩份要同步**，後者靠 `pyproject.toml` force-include 打包進 wheel |
| `agent-workspace/agent_helpers.py` | agent 可自編的擴充點，每次 script 自動載入（daemon 需 restart 才吃到變更） |
| `scripts/voice_session.py` | 實驗性 voice session（需 `XAI_API_KEY`，非 Grok Build 登入） |
| `scripts/observe-demo.sh` | 密集截圖觀察 loop（presence/視覺迭代用） |
| `desktop-harness`（sh） | dev launcher：不安裝直接跑 working tree |

## 3. 資料流

### 3.1 一次典型的控制呼叫

```
desktop-harness <<'PY'            使用者/agent 下指令
  click_text("Save")
PY
   │
   ▼ run.py
   ├─ daemon 在跑？→ client_request({"op":"exec", code, token})
   │                  └→ daemon.exec → helpers namespace 內執行
   └─ 沒跑 → 本地 exec（同一個 namespace）
   │
   ▼ helpers.click_text
   ├─ safety gate（敏感 app？frontmost 檢查）
   ├─ activate(app)（已在前景則跳過——latency 優化 + audit activate_skip）
   ├─ ax.find(text)          ← 走訪 AX tree，配分：exact > startswith > 最短 substring
   ├─ 命中 → 偏好 AXPress（元素動作）；否則 → 座標 fallback（input.click）
   ├─ wait_stable / settle sleeps
   └─ audit → ~/.desktop-harness/audit.jsonl
   │
   ▼ （agent 義務）verify("…") → 讀回傳的 PNG 路徑（ADR-0009）
```

### 3.2 感知 fallback 鏈（ADR-0001）

`labels()`/`ax_snapshot()`（AX，快）→ 失敗/空乏 → `screenshot()`（window 優先；unique 檔名）→ 視覺判讀（agent 端，最後手段）。

### 3.3 daemon 生命週期

`daemon start --bg` → 寫 token（0600）→ bind socket（chmod 0600）→ PID file → accept loop（**單執行緒**）→ 每請求驗 token → exec / ping / quit → 收尾清 socket+PID。CLI 每次先 ping（timeout 0.4s）判斷 daemon 活著沒；`DH_NO_DAEMON=1` 略過。

## 4. 環境設定（開發機）

```bash
git clone … && cd desktop-harness
./desktop-harness --version        # dev launcher，不需安裝
python3 -m venv .venv && source .venv/bin/activate
pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices
pip install -e . --no-deps
desktop-harness --doctor           # 先過這關再說
desktop-harness selftest           # 非破壞性全鏈路
```

權限（System Settings → Privacy & Security）：**Accessibility**（AX 讀取 + 輸入注入）與 **Screen Recording**（截圖；授予後**完整重啟** terminal host）。兩者都給「跑指令的那個 host」（Ghostty / Terminal / Grok）。

## 5. 常見修改路徑

| 我想… | 動哪裡 | 注意 |
|-------|--------|------|
| 加一個新 helper | `helpers.py` 定義 +（若屬變異動作）接 `safety` gate + `audit` | 對外承諾 = `SKILL.md` 兩份都要更新 |
| 改 AX 配對/走訪 | `ax.py`（`find` 配分、walk 的 interactive filter） | 配分規則是事故學費（ADR-0007）；`Play` vs `Play all` 類回歸要測 |
| 改 app 尋找/啟動 | `windows.py`（`find_app` 的 exact > startswith > 最短 substring 順序） | 勿退回 first-hit substring；短 query 特別危險 |
| 改截圖 | `capture.py` | 檔名必須維持 unique（並發不覆蓋）；記得 gate（ADR-0008：截圖=點擊同級） |
| 改滑鼠/鍵盤 | `input.py`（CGEvent） | 真實 HID、會搶 focus；settle sleeps 是延遲 vs 可靠性的取捨 |
| 改 presence | `presence.py` | **main-thread 鐵律**（ADR-0006）；驗收必須跑 observe loop（跨 app 點擊 + 數秒閒置 + 多影格） |
| 改 daemon | `daemon.py` | 認證不可退；測試用 `DH_SOCKET`/`DH_TOKEN_PATH` 指到 tmp |
| 改安全規則 | `safety.py` | 敏感清單分 name/bundle 兩 tuple；`DH_ALLOW_SENSITIVE` 逃生口只有一個 |
| 改 agent 教學 | `SKILL.md` **和** `src/desktop_harness/data/SKILL.md`（同步） | wheel 打包只取後者 |
| 加 voice 工具 | `voice_tools.py`（TOOL_DEFINITIONS + execute） | 8–15 個小而清楚的 tool 優於一堆 raw API；`run_shell` 預設不提供 |

## 6. 陷阱（依痛的程度排序）

1. **AppKit 跨執行緒 = SIGABRT，不是 exception。** 在背景 thread 碰 window/view，整個 process 直接死，無法恢復。長等待用分片 wait（`presence.keep_alive()`），不要開 thread（ADR-0006）。
2. **「沒丟例外」不等於「畫面對了」。** 變異動作後必 `verify()` 並讀圖（ADR-0009）。自己寫 agent 流程時同理。
3. **Space 是 toggle。** 任何媒體/播放控制先 `media_transport()` 讀狀態，只做一次動作（ADR-0007）。這條規則來自一次在真實使用者面前播放-暫停-播放-跳歌的事故。
4. **安全 gate 只包 helper 路徑。** script 裡 `import subprocess` 就繞過一切（ADR-0003 的既定界限）。所以「新增變異 helper」永遠要補 gate；「宣稱安全」永遠要打折。
5. **daemon 的 namespace 只載入一次。** 改 `agent-workspace/agent_helpers.py` 後要 `daemon stop && daemon start`，否則永遠跑到舊版。
6. **兩份 SKILL.md 會漂移。** repo 根目錄與 `data/` 那份；忘記同步 = 安裝版 skill 行為與 repo 不同。
7. **`find_app` 不要退回 first-hit substring。** `"Text"` 會配到第一個名字含 text 的 app。現行排序（exact > 唯一 startswith > 最短 substring）是刻意的。
8. **座標點擊要目標 app 在前景。** 沒有背景 focus-free 控制（roadmap 項目）；文件不可過度承諾。
9. **Electron/canvas 是二級公民。** AX 稀疏只能退截圖；這是 known limit，不是你要修的 bug（除非 roadmap 說要修）。
10. **多監幕器的 overlay 座標變換**已知有疑慮（review #12），宣稱前先驗證。
11. **驗收 UI 動態行為不能靠單張截圖。** presence 曾在「focus 跳走後靜默消失」的狀態下出貨過——用 `scripts/observe-demo.sh` 拍多影格，序列必須含跨 app 點擊與純閒置。
12. **測試不要碰使用者的真實環境。** socket/token/audit 用環境變數指到 `tmp_path`；自我測試相關的假憑證一律用明顯假字串，勿用真實格式前綴。

## 7. 驗證你的修改

```bash
desktop-harness --doctor      # 權限鏈
desktop-harness selftest      # 全鏈路（含 daemon 往返、TextEdit 打字）
desktop-harness demo          # 人眼看的冒煙測試（真的會動滑鼠！）
./scripts/observe-demo.sh /tmp/dh-observe   # 動態 UI（presence）專用
```

發佈前另見 `RELEASE.md` 與 `docs/PRE-RELEASE-REVIEW.md` 的 checklist（該 review 的許多項目已修復——daemon token、mutation gate、unique screenshot、版本對齊——但其「測試清單」仍是好的回歸基準）。

## 8. 深入閱讀順序

`README.md` → `HOW_IT_WORKS.md`（白話）→ `DESIGN.md`（架構）→ 本目錄 ADR（為什麼）→ `docs/POSTMORTEM-media-play.md` + `docs/OBSERVE-LOOP.md`（事故與教訓）→ `docs/PRE-RELEASE-REVIEW.md`（已知債與邊界）。
