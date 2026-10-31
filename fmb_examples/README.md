# desktop-harness 離線可執行範例

本目錄提供 5 個 `desktop-harness` 使用範例。所有範例皆可從 repository 根目錄直接執行，不會呼叫 HTTP/WebSocket 服務、不需要真實金鑰，也不會更新或查詢線上版本。

## 使用前提

- macOS 與 Python 3.10 以上。
- `desktop-harness` 的宣告依賴已安裝在 repository 的 `.venv`，或安裝於目前 Python 環境。
- 需要操作真實桌面或 Accessibility API 的範例，需要替執行該腳本的終端機／代理宿主授予「輔助使用」權限。
- 本組範例不需要螢幕錄製權限，也不會擷取螢幕。

執行前先切換至 repository 根目錄：

```bash
cd /path/to/desktop-harness
```

## 範例總覽

| 範例 | 用途 | 是否操作真實桌面 | 是否需要憑證 |
|---|---|---:|---:|
| `01_read_only_discovery.py` | 唯讀列出應用程式、視窗與前景程式統計 | 否 | 否 |
| `02_ax_edit_verify.py` | 在暫存文字檔中輸入假值，以 Accessibility tree 驗證後關閉文件 | 是，僅 TextEdit | 否 |
| `03_mouse_restore.py` | 移動滑鼠後立即移回原位，不點擊任何控制項 | 是，僅滑鼠 | 否 |
| `04_daemon_roundtrip.py` | 使用隔離的 Unix socket 啟動 daemon，執行算式並停止 | 否 | 否；token 僅在暫存目錄產生 |
| `05_voice_dry_run.py` | 以假 API key 預覽 Voice tool schema 與 dry-run 結果 | 否 | 假值 `FAKE_VALUE_FOR_TEST` |

## 1. 唯讀探索

用途：示範 `list_apps()`、`list_windows()` 與 `frontmost_app()` 的基本探索方式。輸出只包含數量，不會列出應用程式名稱或視窗標題。

```bash
python3 fmb_examples/01_read_only_discovery.py
```

預期輸出格式：

```text
EXAMPLE_RESULT={"apps":...,"frontmost_detected":true,"windows":...}
PASS: read-only discovery completed
```

## 2. AX-first 編輯與驗證

用途：示範「先開啟暫存檔、輸入假值、從 Accessibility tree 驗證，再儲存與關閉」的流程。

- 暫存檔由 `tempfile.TemporaryDirectory()` 建立，結束後自動刪除。
- 輸入內容固定為 `FAKE_VALUE_FOR_TEST`，不含真實或客戶資料。
- 程式只輸出 AX 節點數與驗證結果，不輸出 AX 節點內容。
- TextEdit 需要輔助使用權限；畫面不會被截圖。

```bash
python3 fmb_examples/02_ax_edit_verify.py
```

預期輸出格式：

```text
EXAMPLE_RESULT={"ax_nodes_scanned":...,"marker_verified":true,"temporary_file_used":true}
PASS: AX edit verification completed
```

若 TextEdit 未安裝、未取得輔助使用權限，或焦點被其他宿主搶走，範例會以非零狀態結束並顯示原因。

## 3. 滑鼠往返

用途：示範讀取 `mouse_pos()`、安全移動以及還原位置。範例不會點擊、輸入或捲動。

```bash
python3 fmb_examples/03_mouse_restore.py
```

預期輸出格式：

```text
EXAMPLE_RESULT={"distance_moved_px":...,"restored":true}
PASS: mouse position restored
```

## 4. 本機 daemon 往返

用途：示範 daemon 的本機 Unix socket、`ping`、`exec` 與 `quit` 流程。

- socket、token、audit log 全部位於 `tempfile.TemporaryDirectory()` 建立的隔離目錄。
- daemon 自動產生的隨機 token 不會被輸出，也不會沿用正式環境的 token。
- 執行內容只是 `print(6 * 7)`，不會操作桌面。
- 結束時一定會送出 `quit`；若 daemon 未正常退出，程序會將其終止。

```bash
python3 fmb_examples/04_daemon_roundtrip.py
```

預期輸出格式：

```text
EXAMPLE_RESULT={"daemon_roundtrip":"PASS","exec_result":42,"network":"not_used"}
PASS: isolated daemon round-trip completed
```

## 5. Voice tool dry-run

用途：示範 Voice tool 定義及 `execute(..., dry_run=True)`，但完全不啟動麥克風或連線。

此範例只在子程序環境中設定：

```text
XAI_API_KEY=FAKE_VALUE_FOR_TEST
```

此值是明確的假憑證，不會被傳送、印出或寫入磁碟。範例直接使用 `desktop_harness.voice_tools`，因此即使環境中已有其他 API key，也不會呼叫 Voice WebSocket。

```bash
python3 fmb_examples/05_voice_dry_run.py
```

預期輸出格式：

```text
EXAMPLE_RESULT={"fake_credential":true,"network":"not_used","tool_count":...,"tools_checked":2}
PASS: Voice dry-run completed without network access
```

## 一次執行全部範例

```bash
for example in fmb_examples/0*.py; do
  echo "==> $example"
  python3 "$example" || exit 1
done
```

此命令會操作 TextEdit 與滑鼠，但不會點擊外部按鈕、輸入真實資料、連線或使用真實憑證。

## 語法檢查

不需要 macOS 桌面權限，也不會啟動任何 helper：

```bash
python3 -m compileall -q fmb_examples
```
