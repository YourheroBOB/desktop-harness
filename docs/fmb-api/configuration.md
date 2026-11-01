# 設定項參考（環境變數）

依任務規範，本文件**只列變數名與效果，不寫入任何值**。預設的檔案系統位置（audit log、daemon socket／token／pid、截圖目錄）請見 [ARCHITECTURE.md §4.3](../fmb/ARCHITECTURE.md)。

| 變數 | 效果 |
|------|------|
| `DH_NO_DAEMON` | 啟用時一律以本機行程執行腳本，不連線、不啟動常駐 daemon。 |
| `DH_MOUSE_INSTANT` | 啟用時滑鼠移動為瞬移（不做動畫補間）。 |
| `DH_PRESENCE` | 控制 presence 視覺提示（游標光環＋「Agent active — hands off」橫幅）；預設開啟，停用時關閉。 |
| `DH_SAFE` | agent 安全政策開關；預設開啟。 |
| `DH_ALLOW_SENSITIVE` | 啟用時解除敏感 app（密碼管理器類）的開啟／聚焦阻擋，以及前台敏感時的變更與截圖阻擋；預設關閉，**勿隨意開啟**。 |
| `DH_AUDIT_LOG` | 覆寫 audit log 檔案路徑。 |
| `DH_SOCKET` | 覆寫 daemon Unix socket 路徑（測試請指向 `tmp_path`／`tempfile`）。 |
| `DH_TOKEN_PATH` | 覆寫 daemon token 檔案路徑（測試請指向 `tmp_path`／`tempfile`）。 |
| `XAI_API_KEY` | （實驗性語音）xAI Realtime API 金鑰——**屬機密**，只能放在環境或 Keychain，切勿寫入 repo 或任何文件；無此金鑰且未用 `--dry-run` 時 `voice_session.py` 會明確退出。 |
| `GROK_VOICE_MODEL` | （實驗性語音）覆寫 Realtime 模型名稱。 |

## 敏感應用阻擋（與 `DH_ALLOW_SENSITIVE` 連動）

- 預設**阻擋**開啟／聚焦密碼管理器類 app；當這類 app 在前景時，阻擋變更動作（點擊／打字／快捷鍵／設值）與**截圖**（拍下可見密碼與點進去是同等級洩漏，見 [ADR-0008](../fmb-adr/ADR-0008-sensitive-app-gates.md)）。
- 僅在設定 `DH_ALLOW_SENSITIVE` 時放行。安全模型詳見 [SECURITY.md](../../SECURITY.md)。

## Audit log

- 記錄關鍵變更（如 `activate`、`click_text`、`screenshot`、`ensure_media_playing`）的時間戳與參數；**不記錄輸入內容字串**（詳見 `safety.audit()` 與 `DH_AUDIT_LOG`）。
- 目前無輪替／保留策略（已知議題，見 [fmb-perf TR-4](../fmb-perf/findings-timeouts-recovery.md)）。

## 測試用的假憑證規範

- 任何需要 token／key 的測試或範例，一律使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串；不可使用 `sk-`、`ghp_`、`xox` 等真實格式前綴。
- 測試不得連線網路正式服務；daemon 相關測試以 `DH_SOCKET`／`DH_TOKEN_PATH` 指向 `tmp_path`／`tempfile`。
