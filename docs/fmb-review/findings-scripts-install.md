# 審查發現：`install.sh`／`scripts/observe-demo.sh`／`desktop-harness`

> 行號以 v0.4.2 快照為準。錨點建議搭配 `grep -n` 確認。

---

## A. `install.sh`（INS-*）

### INS-1｜無條件覆寫 `~/.local/bin/desktop-harness`

- **位置：** `install.sh:18-23`
- **嚴重度：** P2（破壞性／使用者信任）
- **說明：** `cat > "$HOME/.local/bin/desktop-harness"` 不看原本有沒有東西。若使用者已有一個自己的 `desktop-harness`（另一個 checkout 的 shim、或同名工具），會被靜默取代，且沒有備份。安裝腳本對 `$HOME` 的寫入應該預設「不摧毀」。
- **建議修法：**

```bash
shim="$HOME/.local/bin/desktop-harness"
if [ -e "$shim" ] && ! grep -q "desktop-harness/.venv" "$shim" 2>/dev/null; then
  echo "==> $shim 已存在且非本專案 shim，保留不動" >&2
  echo "==> 本安裝的進入點：$ROOT/.venv/bin/desktop-harness" >&2
else
  cat > "$shim" <<EOF
#!/bin/sh
exec "$ROOT/.venv/bin/desktop-harness" "\$@"
EOF
  chmod +x "$shim"
fi
```

- **工作量：** S（1h）

### INS-2｜SKILL.md 直接重導向寫入，失敗留半份

- **位置：** `install.sh:28`
- **嚴重度：** P2（錯誤恢復）
- **說明：** `desktop-harness skill > ~/.grok/skills/desktop-harness/SKILL.md`。若 CLI 在中間失敗（`set -e` 會中止），留下的是**半份 SKILL.md**，而 Grok 下次開工就讀到殘檔——agent 會拿到不完整的行為規範。寫入共享位置應原子化。
- **建議修法：**

```bash
tmp_skill="$(mktemp "$HOME/.grok/skills/desktop-harness/SKILL.md.XXXXXX")"
"$ROOT/.venv/bin/desktop-harness" skill > "$tmp_skill"
mv "$tmp_skill" "$HOME/.grok/skills/desktop-harness/SKILL.md"
```

- **工作量：** S（0.5h）

### INS-3｜無 macOS / Python 版本 preflight

- **位置：** `install.sh:3-16`
- **嚴重度：** P2（可攜性／錯誤訊息品質）
- **說明：** 腳本在 Linux 上會一路跑到 `pip install pyobjc-*` 才炸，錯誤訊息是 pip 的「no matching distribution」，完全沒提示「此工具只支援 macOS」。Python < 3.10 也是到 import 階段才死。
- **建議修法：**

```bash
[ "$(uname -s)" = "Darwin" ] || { echo "install.sh: 僅支援 macOS" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "install.sh: 找不到 python3" >&2; exit 1; }
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "install.sh: 需要 Python >= 3.10（目前 $(python3 -V 2>&1)）" >&2; exit 1; }
```

- **工作量：** S（1h）

### INS-4｜`--doctor || true` 使安裝永遠 exit 0

- **位置：** `install.sh:41`
- **嚴重度：** P2（可測試性／CI）
- **說明：** 授權尚未給齊時 doctor 本來就會失敗，`|| true` 是有意的。但副作用是 install.sh 無法當 CI gate——壞掉的安裝也會「成功」。需要一條明確的嚴格模式開關。
- **建議修法：**

```bash
if [ "${DH_INSTALL_STRICT:-0}" = "1" ]; then
  "$ROOT/.venv/bin/desktop-harness" --doctor
else
  "$ROOT/.venv/bin/desktop-harness" --doctor || true
fi
```

並在 RELEASE.md 的 checklist 改用 `DH_INSTALL_STRICT=1 ./install.sh`。
- **工作量：** S（0.5h）

### INS-5｜shim 內建絕對路徑，clone 搬移即失效

- **位置：** `install.sh:21`
- **嚴重度：** P2（可攜性）
- **說明：** shim 寫死 `$ROOT`。使用者把 repo 從 `~/dev/desktop-harness` 移到別處，shim 的 exec 會失敗，訊息是 `no such file or directory`——看不出跟搬移有關。
- **建議修法：** 短期在 shim 加一行存在性檢查與提示；長期（roadmap 的 .app onboarding）再改為解析 symlink。文件補一句「搬移 clone 後請重跑 install.sh」。
- **工作量：** S（0.5h + 文件）

### INS-6｜重跑安裝沿用可能損壞的 `.venv`

- **位置：** `install.sh:8`
- **嚴重度：** P2（冪等性）
- **說明：** 若 `.venv` 是用不同 Python 版本建立、或之前安裝中斷，`python3 -m venv .venv` 不會修好它，接下來的 pip 行為難以預期。
- **建議修法：**

```bash
if [ "${DH_INSTALL_FORCE:-0}" = "1" ]; then rm -rf "$ROOT/.venv"; fi
python3 -m venv --upgrade-deps "$ROOT/.venv" 2>/dev/null || python3 -m venv "$ROOT/.venv"
```

- **工作量：** S（0.5h）

### INS-7｜pip 相依未鎖版本下限

- **位置：** `install.sh:12-16`（另見 PKG-1）
- **嚴重度：** P2（相依風險）
- **說明：** 三個 pyobjc framework 裝 latest。pyobjc 大版本常隨 macOS SDK 變動，未來某次重跑 install.sh 可能裝到不相容版本，讓舊 clone 突然壞掉。下限（floor）不鎖死版本，只擋「太舊」。
- **建議修法：** 與 `pyproject.toml` 同步加下限（保守 `>=10.0`，實作當天以 venv 實際版本校準）：
  `pip install -q "pyobjc-framework-Quartz>=10.0" ...`
- **工作量：** S（0.5h）

### INS-8｜venv／pip 失敗訊息未包裝

- **位置：** `install.sh:8-16`
- **嚴重度：** P2（錯誤處理）
- **說明：** venv 建立失敗（常見原因：Xcode CLT 缺、磁碟滿、`python3` 是 conda shim）只拿到 pip/venv 的原始錯誤。
- **建議修法：** 每步包一層 `|| { echo "install.sh: <步驟> 失敗（$?）" >&2; exit 1; }`，或抽 `die()` 函式統一處理。
- **工作量：** S（1h）

---

## B. `scripts/observe-demo.sh`（OBS-*）

### OBS-1｜預設輸出固定路徑，併發互撞

- **位置：** `scripts/observe-demo.sh:5-7`
- **嚴重度：** P2（測試隔離）
- **說明：** `OUT="${1:-/tmp/dh-observe}"` 固定名稱；兩個觀察迴圈同時跑（或與前次殘檔）會互相 `rm`／覆蓋。另 `rm -f "$OUT"/*.png` 對「使用者傳空字串」的防護依賴 `mkdir -p ""` 先失敗，屬於意外安全而非設計安全。
- **建議修法：**

```bash
OUT="${1:-${TMPDIR:-/tmp}/dh-observe-$$}"
[ -n "$OUT" ] || { echo "usage: observe-demo.sh [outdir]" >&2; exit 2; }
mkdir -p "$OUT"
```

- **工作量：** S（0.5h）

### OBS-2｜`screencapture` 失敗被靜默吞掉

- **位置：** `scripts/observe-demo.sh:17`
- **嚴重度：** P2（錯誤處理）
- **說明：** `screencapture -x ... || true`——沒有 Screen Recording 權限時 24 幀全失敗，腳本只在最後一行印 `frames: 0`。觀察迴圈的整個價值在影格，零影格應該在**開始時**就失敗並給授權提示。
- **建議修法：**

```bash
probe="$OUT/_probe.png"
if ! screencapture -x "$probe" 2>/dev/null || [ ! -s "$probe" ]; then
  echo "screencapture 失敗：請到 系統設定 > 隱私權與安全性 > 螢幕錄製 勾選終端機後重啟" >&2
  exit 1
fi
rm -f "$probe"
```

- **工作量：** S（0.5h）

### OBS-3｜固定座標點擊會點到開發者當下畫面的任何東西

- **位置：** `scripts/observe-demo.sh:39-41`（`click(520, 420, ...)`）
- **嚴重度：** **P1**（安全／正確性）
- **說明：** 這是開發者工具，但「在 520,420 連點兩次」是對真實桌面的操作。如果那一刻那裡是「刪除」按鈕、是通訊軟體的傳送、是未儲存檔案的「不儲存」——腳本照點。SKILL.md 的 consent 原則對工具自己也該成立。另 ADR-0009 要求變更畫面後 verify，此腳本也沒有。
- **建議修法：**

```bash
: "${DH_OBSERVE_CLICK_XY:=520,420}"
IFS=, read -r CX CY <<<"$DH_OBSERVE_CLICK_XY"
echo "!! 3 秒後會在 ($CX,$CY) 真實點擊兩次；Ctrl-C 可中止" >&2
sleep 3
```

Python 段改用 `click(float(CX), float(CY), ...)`（由 env 讀入），讓 CI／安全的環境可把座標指到 TextEdit 內部或完全關閉點擊（`DH_OBSERVE_CLICK_XY=none`）。
- **工作量：** S（2h）

### OBS-4｜venv activate 失敗靜默退回系統 CLI

- **位置：** `scripts/observe-demo.sh:24`
- **嚴重度：** P2（錯誤處理）
- **說明：** `source .venv/bin/activate 2>/dev/null || true`——沒有 venv 時用系統 `desktop-harness`，可能是半年前的 release，行為與目前 repo 不同，觀察結果誤導。
- **建議修法：** activate 失敗就 `exit 1` 並提示先跑 `./install.sh`。
- **工作量：** S（0.5h）

### OBS-5｜捕捉視窗與 demo 時長未對帳

- **位置：** `scripts/observe-demo.sh:15-16` vs `:30-42`
- **嚴重度：** P2（可讀性／可維護性）
- **說明：** 24 × 0.28s ≈ 6.7s 的捕捉視窗 vs demo 約 6–7s 的動作序列，兩個數字沒有共用來源，改一邊另一邊靜默失配。（正向：目前尾巴正好覆蓋「點擊後閒置」，符合 SKILL.md 對 presence 的多影格要求——請在註解寫明這個意圖，免得有人「最佳化」掉。）
- **建議修法：** 把 `FRAMES=24`、`INTERVAL=0.28` 提為變數並加註解；結尾明確保留 1–2s 空拍給 idle frame。
- **工作量：** S（0.5h）

---

## C. `desktop-harness` dev launcher（LAU-*）

### LAU-1｜symlink 呼叫時 `PYTHONPATH` 解析錯誤

- **位置：** `desktop-harness:3`
- **嚴重度：** P2（正確性）
- **說明：** `DIR="$(cd "$(dirname "$0")" && pwd)"` 取的是 `$0` 所在目錄。若使用者把 launcher symlink 到 `~/bin/desktop-harness`，DIR 變成 `~/bin`，`PYTHONPATH=~/bin/src` 不存在 → `No module named desktop_harness`。（install.sh 的 shim 用絕對路徑呼叫所以沒事，但文件鼓勵直接把 repo 的 launcher 掛上 PATH 的用法會中獎。）
- **建議修法（POSIX 可攜；不可對 `$0` 賦值，改用 `target` 變數迭代解析 symlink）：**

```sh
target="$0"
while [ -L "$target" ]; do
  link="$(readlink "$target")"
  case "$link" in
    /*) target="$link" ;;
    *)  target="$(dirname "$target")/$link" ;;
  esac
done
DIR="$(cd "$(dirname "$target")" && pwd)"
```

- **工作量：** S（1h）

### LAU-2｜`.venv/bin/python` 損壞時錯誤訊息晦澀

- **位置：** `desktop-harness:4-8`
- **嚴重度：** P2（錯誤處理）
- **說明：** venv 存在但 python 被移／損，`-x` 通過、exec 失敗，只拿到 exec 的錯誤。
- **建議修法：** `"$DIR/.venv/bin/python" -c 'import sys' 2>/dev/null || PYTHON=python3`，並在 fallback 時印一行 warning 到 stderr。
- **工作量：** S（0.5h）

### LAU-3｜未檢查 Python 版本

- **位置：** `desktop-harness:7`
- **嚴重度：** P2（可讀性）
- **說明：** `requires-python = ">=3.10"` 只存在 pyproject；裸 `python3` fallback 路徑沒有對應檢查，<3.10 的系統會在 import 階段才炸。
- **建議修法：** fallback 前做一次版本檢查，失敗給明確訊息（與 INS-3 同一段邏輯可抽成共享腳本）。
- **工作量：** S（0.5h）

---

## 正面觀察（值得保留）

- 兩個腳本都有 `set -euo pipefail`；observe 腳本明確 `DH_NO_DAEMON=1`、`DH_PRESENCE=1`，測試意圖清楚。
- install.sh 對 Grok skill 採「存在 `~/.grok` 才註冊」的保守策略，沒有亂寫使用者目錄。
- 腳本內無任何 secrets、無網路下載執行（curl|bash）模式。
