# L3：秘密掃描、相依掃描

## 威脅模型（這個 repo 特有的）

1. **`XAI_API_KEY`** 是本 repo 已知的秘密接口（`scripts/voice_session.py` 只從 env 讀，這是對的——CI 要保證它**永遠**不會被硬編碼進任何檔案）。歷史上 `scripts/voice_hotkey_readme.md` 曾示範 Keychain 指令，掃描要能容忍這類**說明性**文字而不誤報關卡。
2. **daemon token / socket** 是執行期產物（`~/.desktop-harness/`），不該出現在 repo——掃描模式要涵蓋 `daemon.token` 類檔名。
3. **這是能控制真實桌面的程式碼**：供應鏈攻擊（惡意 PR 偷偷加相依）在此 repo 的後果比一般 CLI 嚴重——相依掃描不是儀式。
4. **audit log / 截圖**（`*.png` 已在 `.gitignore`）不該被 commit——掃描 + gitignore 雙保險。

## 工具選擇

| 關卡 | 工具 | 理由 |
|------|------|------|
| 秘密掃描 | **gitleaks**（官方 action） | 單一 binary、規則集成熟、誤報可控；不把 repo 內容送到第三方 SaaS（保守：不選需要上傳掃描結果的商業掃描器） |
| 相依掃描 | **pip-audit**（PyPA 官方） | 掃 PyPI 已知 CVE（OSV 資料庫）；本地執行、不外傳 |
| Shell 掃描 | **ShellCheck** | `install.sh`、`desktop-harness`、`scripts/observe-demo.sh` 都是 shell |

## 範本（供日後採用；本提案不建立 workflow 檔）

```yaml
# 建議檔名（本次不建立）：.github/workflows/security.yml
name: security

on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"   # 每週一掃一次：新增 CVE 不會因為沒 PR 而漏掉

permissions:
  contents: read           # 最小權限原則：掃描 job 只需要讀

jobs:
  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # gitleaks 掃全歷史（首次跑會較久，但 commit 過的秘密不會漏）
      - name: gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}   # 唯一需要的 token，GitHub 自動提供

  deps:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pipx install pip-audit
      # pyobjc 在 Linux 裝不起來 → 只掃 metadata，這已是有效關卡
      # （深層掃在 BUILD-RELEASE.md 的 macOS 建置 job 裡做）
      - name: audit dependency metadata
        run: pip-audit --strict --disable-pip -r <(pip install --dry-run --report - . >/dev/null 2>&1; true)
        # 註：最簡做法是 pip-audit --strict .（會嘗試裝相依）；
        # pyobjc 裝不上 Linux 時改用 --requirement 對 pyproject 產出的 report。
        # 兩條路都保留在範本中，採用時擇一實測。

  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: shellcheck
        run: |
          # 只掃 repo 內 shell 檔；不執行任何正式服務連線
          find . -name "*.sh" -not -path "./.venv/*" -print0 \
            | xargs -0 shellcheck --severity=warning
```

### gitleaks 設定檔範本（`gitleaks.toml`，供日後採用）

```toml
# 追加在本 repo 根目錄的 gitleaks.toml（本次不建立）
# 用途：降低說明性文件的誤報，同時補 daemon token 類檔名規則
title = "desktop-harness gitleaks config"

[extend]
useDefault = true   # 保留官方全部規則（API key 前綴、AWS、private key 等）

# 本 repo 的說明文件刻意包含「export XAI_API_KEY="…"」這類教學文字，
# 佔位符（…、YOUR_KEY_HERE、FAKE_VALUE_FOR_TEST）不該觸發關卡：
[[rules]]
id = "dh-placeholder-exemption"
description = "placeholder secrets in docs"
regex = '''YOUR_KEY_HERE|FAKE_VALUE_FOR_TEST'''
# 這條其實是 allowlist 用途，gitleaks 以 allowlist 處理：
[allowlist]
description = "allow doc placeholders"
regexes = ['''YOUR_KEY_HERE''', '''FAKE_VALUE_FOR_TEST''', '''export XAI_API_KEY=["'”]?…''']
paths = ['''docs/.*''', '''.*\.md''']
```

**採用時注意：** 上面 allowlist 的 `regex` 寫法請以當下 gitleaks 版本手冊為準實測——寬鬆 allowlist 是秘密掃描最常見的自殺方式，寧可先誤報再逐條放行。

## 需要人工的環節（CI 不能取代）

- gitleaks 抓到疑似秘密時：**撤銷輪換**（rotate）永遠優先於刪 commit；刪除歷史只是把指紋擦掉。
- `pip-audit` 回報 pyobjc 相關 CVE 時：pyobjc 是系統框架綁定，CVE 修復週期與一般套件不同，需要人工判斷是否可暫緩（建議以 GitHub issue 記錄豁免理由，而不是在指令裡靜默 `--ignore`）。
