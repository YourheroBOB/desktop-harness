# 安裝與部署

## 前置需求

- macOS（建議 Sequoia 以上；較舊版本可能可用但未承諾）
- Python 3.10+
- 可寫入 `~/.local/bin` 與 `~/.desktop-harness/`
- 使用者具備授權 **Accessibility** 與 **Screen Recording** 給執行 host（Terminal / Ghostty / iTerm / Grok host）的能力

## 標準安裝（install.sh）

```bash
git clone <repo-url> && cd desktop-harness
chmod +x install.sh && ./install.sh
export PATH="$HOME/.local/bin:$PATH"
```

`install.sh` 會執行：

1. 在 repo 內建立 `.venv/` 並安裝 pyobjc 三個 framework 依賴
2. `pip install -e . --no-deps`（editable 安裝）
3. 產生 `~/.local/bin/desktop-harness` shim（指向 repo 的 venv）
4. 若 `~/.grok` 存在，註冊 Grok skill 到 `~/.grok/skills/desktop-harness/SKILL.md`
5. 結尾自動執行一次 `--doctor`（失敗不中斷安裝）

## 手動安裝

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices
pip install -e . --no-deps
mkdir -p ~/.local/bin
ln -sf "$(pwd)/.venv/bin/desktop-harness" ~/.local/bin/desktop-harness
```

## 權限設定（一次性）

```bash
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
```

- 勾選「實際執行指令的 host」（Terminal、Ghostty、iTerm 或 Grok host），不是勾 Python 本身。
- 授予 Screen Recording 後必須**完全退出並重啟該 host**，權限才生效。

## 部署後驗證

```bash
desktop-harness --doctor     # 需全數 PASS
desktop-harness selftest     # 需全數 PASS（含 TextEdit 打字與 daemon 往返）
desktop-harness --version    # 確認版本一致
```

## 選配元件部署

### Warm daemon（建議多用於多步驟 agent 任務）

```bash
desktop-harness daemon start --bg
desktop-harness daemon status
# 用完 / 長時間不用時：
desktop-harness daemon stop
```

部署注意：

- daemon 啟動時會寫入/更新 token 檔（路徑由設定決定，權限 0600），socket 亦為 0600。
- 單一執行個體：已有存活的 daemon 時再次 `start` 會被拒絕，請改用 `status` / `stop`。
- 僅應在單一使用者、非共享的機器上常駐。

### Grok skill

```bash
mkdir -p ~/.grok/skills/desktop-harness
desktop-harness skill > ~/.grok/skills/desktop-harness/SKILL.md
```

### Voice（實驗性、選配）

- 需要 `scripts/voice_session.py`、額外 pip 套件（websockets 等）與 API key 環境變數（變數名見 [02-config.md](./02-config.md)）。
- key 應放環境變數或 Keychain，**絕不**寫入 repo 檔案。
- 部署驗證可用 `--dry-run` / `--list-tools`，不需要網路與 key。

## 更新程序

```bash
cd /path/to/desktop-harness
desktop-harness daemon stop        # 先停 daemon（避免舊命名空間殘留）
git pull
./install.sh                       # 重建 venv + shim + skill
desktop-harness check-update       # 選配：與遠端 main 比對
desktop-harness --version
desktop-harness --doctor && desktop-harness selftest
```

本工具**沒有自動更新**（by design）；更新時機由維運人員掌控。
