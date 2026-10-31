# desktop-harness 資安與可靠性稽核清單（CHECKLIST）

搭配 [AUDIT.md](./AUDIT.md) 使用。狀態圖例：

- ✅ 通過（無需動作）
- ⚠️ 部分通過／有條件通過（見 AUDIT 對應項）
- ❌ 未通過（需修補）
- ❓ 無法驗證（檔案未提供／需執行環境）

## 1. 輸入驗證

| 項目 | 狀態 | 備註 |
|------|------|------|
| daemon JSON 請求解析有錯誤處理（`JSONDecodeError` → 回錯誤不 crash） | ✅ | `daemon.py` |
| daemon 請求大小有上限 | ❌ | A-14 |
| voice tools 引數 JSON 解析失敗有處理 | ✅ | `voice_tools.py execute()` |
| voice `click_xy` / `type_text` 座標與文字無惡意輸入防線 | ❌ | A-07（runtime 無強制） |
| `find_app` 輸入型別（str/int pid）處理正確 | ✅ | `windows.py`（v0.4 已修 PRE-RELEASE-REVIEW #6/#7） |
| AX 節點 frame 過 `frame_on_screen` 過濾 | ✅ | selftest 有測項；`ax.py` 本體 ❓ 待驗（A-21 #6） |

## 2. 命令注入

| 項目 | 狀態 | 備註 |
|------|------|------|
| 無 `shell=True`／字串拼接 subprocess | ✅ | A-19：`open -a` 為 list-form |
| `osascript` 呼叫（selftest）使用固定字串、無使用者輸入插值 | ✅ | `selftest.py` |
| daemon 協議為 JSON，不經 shell | ✅ | 注入概念不適用（exec 即產品功能，見 A-08 誠實性問題） |
| 回歸防護：未來新增 subprocess 呼叫一律 list-form | ⚠️ | 無 lint 規則強制；建議加入 checklist 到 code review 慣例 |

## 3. 路徑穿越／任意路徑寫入

| 項目 | 現況 | 備註 |
|------|------|------|
| `screenshot(path=...)` 任意路徑覆寫 | ❌ | A-10 |
| 截圖暫存目錄權限明確 0700 | ❌ | A-16 |
| audit log 路徑可由 env 覆寫（`DH_AUDIT_LOG`） | ⚠️ | 同 UID 前提下非提權；見 A-04 |
| daemon socket/token/pid 路徑僅在家目錄、不觸及 repo | ✅ | |
| 測試/腳本不讀寫 repo 外路徑 | ✅ | selftest 僅用系統暫存與使用者目錄 |

## 4. 機密外洩風險

| 項目 | 狀態 | 備註 |
|------|------|------|
| repo 內無真實 token／金鑰／密碼／個資 | ✅ | 全檔掃描；僅 `YOUR_KEY_HERE` 佔位符 |
| API key 僅經環境變數／Keychain，不寫入檔案 | ✅ | `voice_session.py`、`voice_hotkey_readme.md` |
| 敏感 app 前景時擋截圖 | ⚠️ | 前景有擋；**可見但非前景**漏檢 → A-05 |
| 敏感 app 前景時擋 mutation | ❓ | 取決於 helpers/input 是否全接上 `check_frontmost_allowed` → A-21 #1 |
| audit log 不記錄輸入欄位值（密碼保護） | ✅ | 維持現況；明文寫入 SECURITY.md（A-20） |
| voice 工具結果（AX labels）外送前有同意提示／截斷 | ❌ | A-06 |
| `.gitignore` 防誤 commit 截圖（`*.png`） | ✅ | 建議補 `daemon.token` |

## 5. 相依套件／供應鏈

| 項目 | 狀態 | 備註 |
|------|------|------|
| 執行期依賴有版本下限與上限 | ❌ | A-09（pyobjc 三件全未釘） |
| install 腳本不盲目 `pip install -U` | ❌ | A-09 |
| 可重現安裝（lockfile／hash pinning） | ❌ | A-09 建議 |
| 無網路服務依賴於核心控制路徑（voice 為選用實驗） | ✅ | voice 需明確 key 才連線 |
| 離線 CVE 掃描 pyobjc | ❓ | 本環境無網路，無法查詢已知 CVE；建議 CI 加 `pip-audit` |

## 6. 錯誤處理

| 項目 | 狀態 | 備註 |
|------|------|------|
| daemon 單一連線例外不影響存活 | ❌ | A-02（BrokenPipe 可殺死 daemon） |
| exec 失敗回傳 traceback 而非斷線 | ✅ | 回 `{"ok":false,...}` |
| `activate` 啟動失敗有明確 RuntimeError | ✅ | `windows.py` |
| doctor 各檢查獨立 try/except、不中斷 | ✅ | `admin.py` |
| `audit()` 失敗靜默 | ❌ | A-04 |
| `check_frontmost_allowed` 例外即放行 | ❌ | A-03（fail-open） |

## 7. 併發

| 項目 | 狀態 | 備註 |
|------|------|------|
| daemon 可同時服務多個連線 | ❌ | A-01（單執行緒序列處理） |
| exec 有執行時間上限（防無限迴圈占住 daemon） | ❌ | A-01 |
| daemon 單實例檢查為原子操作 | ❌ | A-11（TOCTOU） |
| 截圖輸出檔名唯一（並發不互踩） | ✅ | v0.4 已改 `capture-{pid}-{time_ns}.png` |
| presence 跨執行緒 AppKit 使用安全 | ❓ | A-21 #5（OBSERVE-LOOP.md 記載 SIGABRT 風險） |

## 8. Fail-open / Fail-closed

| 項目 | 狀態 | 備註 |
|------|------|------|
| 認證失敗（daemon token）→ 拒絕 | ✅ | fail-closed |
| 權限檢查失敗（frontmost 例外）→ 放行 | ❌ | A-03，應改 fail-closed |
| 稽核寫入失敗 → 靜默繼續 | ❌ | A-04 |
| 截圖敏感檢查漏掉可見非前景視窗 | ❌ | A-05 |
| daemon 不可達 → fallback 本地執行 | ⚠️ | 降級合理但無告警；A-15 建議降低延遲 |
| DH_* 環境變數可被執行中的腳本翻掉 | ⚠️ | 設計使然；文件須誠實（A-08） |

## 9. 可靠性（其他）

| 項目 | 狀態 | 備註 |
|------|------|------|
| `is_running()` ping 逾時 0.4s 偏長 | ❌ | A-15 |
| audit log 有 rotation／上限 | ❌ | A-20 |
| voice session 工具呼叫輪數有上限 | ❌ | A-18 |
| daemon 停止後清除 socket + PID | ✅ | token 未清 → A-13 |
| stale socket 於下次 start 清理 | ✅ | `serve()` unlink；client 端清理 ❌（A-15） |
| 安裝後 `--doctor` 可驗證權限鏈 | ✅ | `install.sh` 末段執行 |

## 10. 待驗證（檔案未提供：run.py / helpers.py / input.py / ax.py / presence.py）

- [ ] ❓ 所有 mutation helper 均接 `check_frontmost_allowed()`（AUDIT A-21 #1）
- [ ] ❓ `check_helper_allowed` 是否仍為死碼（A-08；可見 safety.py 中無呼叫者）
- [ ] ❓ `check-update` 是否 phone-home 及外送內容（A-21 #3）
- [ ] ❓ agent workspace 載入路徑是否已移至 `~/.desktop-harness/`（A-21 #4）
- [ ] ❓ presence 執行緒安全（A-21 #5）
- [ ] ❓ ax.py 座標邊界防護（A-21 #6）

## 建議修復優先序

1. **立即：** A-02、A-03（daemon 存活 + fail-closed）
2. **下一版：** A-01、A-05、A-07、A-08（文件）、A-11
3. **規劃：** A-04、A-06、A-09、A-10、A-12～A-18
4. **驗證後關閉：** A-21 全部項目
