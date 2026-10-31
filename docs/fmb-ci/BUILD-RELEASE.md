# L4–L6：建置、安裝煙霧、發佈關卡

## L4：建置驗證

這個 repo 有兩個歷史包袱讓建置關卡特別值錢：

1. **`SKILL.md` 的 force-include**（`pyproject.toml`）——`desktop-harness skill` 子命令曾因 wheel 沒打包它而壞（review #4）。關卡必須**拆開 wheel 實際檢查** `desktop_harness/data/SKILL.md` 存在。
2. **版本三處不一致的歷史**（review #3）——關卡要比對 `__init__.py` 的 `__version__` 與 `pyproject.toml` 的 `version`。

```yaml
# 建議檔名（本次不建立）：.github/workflows/build.yml
name: build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  build:
    runs-on: macos-latest          # hatchling 建置 + 驗 wheel 都在 macOS
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pipx install build pip-audit

      - name: version consistency
        run: |
          pyv="$(python -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
          pkgv="$(PYTHONPATH=src python -c 'import desktop_harness;print(desktop_harness.__version__)')"
          echo "pyproject=$pyv package=$pkgv"
          test "$pyv" = "$pkgv"

      - name: build wheel + sdist
        run: python -m build

      - name: wheel contains SKILL.md (historical regression guard)
        run: |
          python - <<'PY'
          import zipfile, glob, sys
          whl = glob.glob("dist/*.whl")[0]
          names = zipfile.ZipFile(whl).namelist()
          assert any(n.endswith("desktop_harness/data/SKILL.md") for n in names), \
              f"SKILL.md missing from {whl}: {names[:20]}"
          print("SKILL.md packaged OK")
          PY

      - name: dependency audit (macOS — pyobjc installed here, deep scan possible)
        run: |
          pip install dist/*.whl
          pip-audit --strict

      - name: smoke — fresh venv install from wheel
        run: |
          python -m venv /tmp/smoke-venv
          /tmp/smoke-venv/bin/pip install --quiet dist/*.whl
          /tmp/smoke-venv/bin/desktop-harness --version
          /tmp/smoke-venv/bin/desktop-harness --help
          # skill 子命令：歷史上在非 checkout 環境壞過，必須從 wheel 驗
          test -n "$(/tmp/smoke-venv/bin/desktop-harness skill)"

      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

**注意：** 煙霧測試**不跑** `--doctor` / `selftest` / `demo`——runner 無 GUI 權限，那些留在 RELEASE.md 的人工清單。

## L5→L6：發佈關卡

### 設計原則（從 repo 既有精神推導）

- **「無靜默自動更新」是產品承諾**——引申到 CI：發佈也應該是**明確人工動作**觸發（tag push 或 `workflow_dispatch`），而不是「main 綠了就自動發佈」。
- **RELEASE.md 的 checklist 是既有的人工清單**——CI 能自動化的是其中機器可驗的項目，其餘（doctor、selftest、demo 人眼監看）明確留給人工並在關卡裡 checklist 化。

### 自動 vs 人工對照（RELEASE.md 清單的分工）

| RELEASE.md 項目 | CI 可自動？ | 對應關卡 |
|---|---|---|
| `--doctor` all PASS | ✗（需權限） | 人工；發佈 workflow 用 `workflow_dispatch` input 要求操作者勾選確認 |
| `selftest` / `demo` | ✗（需權限 + 人眼） | 人工，同上 |
| No secrets in repo | ✓ | L3 gitleaks |
| 版本一致 / wheel 可安裝 / skill 可輸出 | ✓ | L4 |
| push 到 GitHub | — | 發佈 workflow 本身 |

### 範本（供日後採用；本提案不建立 workflow 檔）

```yaml
# 建議檔名（本次不建立）：.github/workflows/release.yml
name: release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write      # 建立 GitHub Release 需要；用不到就縮成 read

jobs:
  gate:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      # 重跑核心關卡：發佈不信任「tag 當下 main 是綠的」這個假設
      - run: pipx install ruff mypy build
      - run: ruff check src scripts
      - run: mypy
      - run: pip install -e . pytest && pytest -m "not macos_gui"
      - run: python -m build
      - name: verify tag == package version
        run: |
          tag="${GITHUB_REF_NAME#v}"
          pkgv="$(PYTHONPATH=src python -c 'import desktop_harness;print(desktop_harness.__version__)')"
          test "$tag" = "$pkgv" || { echo "tag $tag != version $pkgv"; exit 1; }
      - uses: actions/upload-artifact@v4
        with:
          name: release-dist
          path: dist/

  # 發佈動作本身（建立 GitHub Release / 上傳 PyPI）建議分開為
  # workflow_dispatch + environment protection rule（需人工 approve），
  # 呼應「無靜默變更」精神。具體上傳步驟與憑證（如 PyPI trusted
  # publishing）由 BOB 決定後再補——本提案刻意不含任何憑證設定。
```

### 發佈前人工清單（發佈 workflow 的 input 勾選項草案）

```markdown
操作者必須在觸發發佈前逐項確認（來自 RELEASE.md，未變動其內容）：
- [ ] 本機 `desktop-harness --doctor` 全 PASS
- [ ] 本機 `desktop-harness selftest` 全 PASS
- [ ] 本機 `desktop-harness demo` 人眼監看通過（滑鼠有動、TextEdit 有字）
- [ ] 已審視本次 diff 中所有會動滑鼠/鍵盤的路徑
- [ ] 版本號已 bump（CI 會驗 tag == version，人工先自檢）
```

## 成本備註

`release.yml` 在 macOS runner 上重跑全套，一次 tag 約數分鐘 macOS 時間——發佈頻率低（本 repo 採人工更新模式），可接受。若未來發佈頻繁，可把 `gate` 的 lint/type 部分改為引用 main 上已通過的結論，只保留「建置 + tag 驗證」重跑。
