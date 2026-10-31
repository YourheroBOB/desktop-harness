# 保存與刪除機制盤點

> 對應個資法 §11（目的達成／期限屆滿應刪除或停止處理）與《非公務機關個人資料檔案安全維護計畫處理辦法》保存期限要求的一般性對照。結論先行：**現況除 observe script 的自我清理外，全系統沒有任何保存期限或刪除機制。**

## 1. 各落地資料的保存現況

| 資料 | 落地位置 | 保存期限 | 自動刪除 | 手動刪除指令 | 依據 |
|------|----------|----------|----------|----------------|------|
| 截圖（screenshot/verify） | `$TMPDIR/desktop-harness/capture-*.png` | ❌ 無限 | ❌ 無 | ❌ 無 | `capture.py`；PERC-3 列為 P1 缺口 |
| doctor 截圖 | `$TMPDIR/dh-doctor.png`（固定檔名） | ❌ 無限 | ❌ 無（每次覆蓋同檔，僅此一檔） | ❌ 無 | `admin.py`；PERC-4 |
| observe loop 影格 | `/tmp/dh-observe/*.png` | 每次 run 開頭 `rm -f "$OUT"/*.png` | ⚠️ 僅執行時清同一輸出目錄 | 使用者自行刪 | `scripts/observe-demo.sh` |
| audit log | `~/.desktop-harness/audit.jsonl` | ❌ 無限成長 | ❌ 無輪替 | ❌ 無（只能手删檔案） | `safety.py`；TR-4/OBS-2 |
| daemon token | `~/.desktop-harness/daemon.token` | daemon 生命週期 | ⚠️ 待確認（daemon stop 行為未在本次視野；ADR-0004 未言明 token 刪除） | 手動 | `daemon.py` |
| daemon socket/pid | `~/Library/Caches/desktop-harness/` | daemon 生命週期 | ⚠️ SIGTERM 不清（DAEMON-6 已知） | 手動 | `daemon.py`；DAEMON-6 |
| Grok skill 檔 | `~/.grok/skills/desktop-harness/SKILL.md` | 永久（非個資，僅文件） | ❌ | 手動 | `install.sh` |

## 2. 路徑覆寫與控管

- `DH_AUDIT_LOG`、`DH_SOCKET`、`DH_TOKEN_PATH` 可覆寫路徑（測試沙箱用）——已有良好慣例。
- 截圖暫存目錄 `capture.TMP` **不可**由環境變數覆寫（`docs/fmb-perf/verification-plan.md` 需 monkeypatch 即證）——資料落地位置不受管理者控管，合規上不利（無法統一導向受管理的保存區）。

## 3. 缺口與建議（刪除/保存面）

| 缺口 | 建議（最保守方向） | 對應 finding |
|------|---------------------|----------------|
| 截圖永不刪除 | 依 fmb-perf PERC-3 的 sweep 方案（上限＋清理）；**另訂保存期限**（建議預設 ≤ 24h 或 N 張上限），期限可由環境變數關閉但預設開啟 | COMP-2 |
| audit 無輪替 | 依 TR-4：大小門檻輪替 + 保留 N 份；文件寫明保留期 | COMP-3 |
| 無「一鍵清除」 | 新增 `desktop-harness purge [--audit] [--captures] [--all]` 子命令，刪除本工具產生的所有落地檔（僅限自家命名模式，勿刪不相關檔） | COMP-5 |
| 無解除安裝清理 | `install.sh` 增加對應 `uninstall` 或文件寫明手動清除清單（`~/.desktop-harness`、`~/Library/Caches/desktop-harness`、`~/.local/bin` shim、skill 檔、`$TMPDIR/desktop-harness`） | COMP-5 |
| 當事人刪除請求無對應 | 因落地資料（截圖/audit）無索引，無法回應「刪除某當事人資料」的請求；建議至少文件化「目前無法做到，需人工介入」的事實，並把當事人請求流程寫入營運層文件 | COMP-5 |
| 截圖目錄不可覆寫 | `capture.TMP` 支援 `DH_CAPTURE_DIR` 覆寫，讓管理者能把保存導向受控位置 | COMP-2 附帶 |

## 4. 結論

保存／刪除是本工具**最大的合規空白**：所有個資落地檔都是「只進不出」。短期先做 purge 子命令＋audit 輪替＋截圖 sweep（三者皆為 S～M 工作量，且前兩項已在 fmb-perf roadmap 具備共識），即可消除最明顯的缺口；保存期限與當事人權利機制需 BOB 決定業務定位後再訂數值。
