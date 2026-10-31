"""回歸測試：版本字串一致性與 SKILL.md 打包。

對應的修復痕跡（docs/PRE-RELEASE-REVIEW.md #3、#4 與 ADR-0002）：
  * 版本曾三處不一致（__init__ / pyproject / README），現以單一來源對齊；
  * `desktop-harness skill` 曾在 site-packages 下壞掉，因為 SKILL.md
    沒被打包；現以 pyproject 的 wheel force-include 帶進
    desktop_harness/data/SKILL.md；
  * console script 入口必須維持 desktop_harness.run:main；
  * 三個 pyobjc framework 必須在 dependencies（缺一 doctor 就 FAIL）；
  * .gitignore 必須擋掉本機產物，避免把 venv/快取/截圖 commit 進來。

純檔案層級檢查，不 import 任何 pyobjc。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import desktop_harness  # noqa: E402


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_version_matches_pyproject():
    text = _read("pyproject.toml")
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, 'pyproject.toml 應有 version = "x.y.z"'
    assert desktop_harness.__version__ == match.group(1)


def test_version_looks_like_a_release():
    assert re.fullmatch(r"\d+\.\d+\.\d+([.\-+][0-9A-Za-z.\-+]*)?", desktop_harness.__version__)


def test_readme_states_shipped_version():
    assert f"v{desktop_harness.__version__}" in _read("README.md")


def test_packaged_skill_md_exists_and_is_not_empty():
    pkg_skill = REPO_ROOT / "src" / "desktop_harness" / "data" / "SKILL.md"
    assert pkg_skill.is_file(), (
        "SKILL.md 必須以 package data 形式存在，否則 "
        "`desktop-harness skill` 在非 source checkout 會 FileNotFoundError"
    )
    text = pkg_skill.read_text(encoding="utf-8")
    assert text.strip()
    assert "desktop-harness" in text


def test_root_skill_md_exists():
    root_skill = REPO_ROOT / "SKILL.md"
    assert root_skill.is_file()
    assert root_skill.read_text(encoding="utf-8").strip()


def test_pyproject_force_includes_skill_for_the_wheel():
    text = _read("pyproject.toml")
    assert "force-include" in text
    assert "desktop_harness/data/SKILL.md" in text


def test_console_script_entry_point_is_stable():
    assert 'desktop-harness = "desktop_harness.run:main"' in _read("pyproject.toml")


def test_pyproject_declares_all_required_pyobjc_frameworks():
    text = _read("pyproject.toml")
    for dep in (
        "pyobjc-framework-Quartz",
        "pyobjc-framework-Cocoa",
        "pyobjc-framework-ApplicationServices",
    ):
        assert dep in text, f"缺少必要相依：{dep}"


def test_gitignore_keeps_local_artifacts_out():
    text = _read(".gitignore")
    for pattern in (".venv/", "__pycache__/", ".pytest_cache/", ".DS_Store"):
        assert pattern in text
