"""Contract tests for version / packaging consistency (no pyobjc needed).

Locks current external behaviour:
  - desktop_harness.__version__ pinned value
  - pyproject.toml [project] version matches the package __version__
  - console-script entry point mapping desktop-harness -> run:main
  - SKILL.md is shipped as package data (hatch force-include) with the
    expected frontmatter
  - README status badge matches the package version
  - wheel packages the src/ layout

Pure file reads inside the repo — no network, no writes.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class VersionPackagingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desktop_harness
        cls.version = desktop_harness.__version__
        cls.pyproject = (_ROOT / "pyproject.toml").read_text()
        cls.readme = (_ROOT / "README.md").read_text()

    def test_version_string_is_pinned(self):
        self.assertEqual(self.version, "0.4.2")

    def test_pyproject_version_matches_package(self):
        m = re.search(r'^version\s*=\s*"([^"]+)"', self.pyproject, re.M)
        self.assertIsNotNone(m, "pyproject must declare a version")
        self.assertEqual(m.group(1), self.version)

    def test_console_script_entry_point_mapping(self):
        self.assertIn(
            'desktop-harness = "desktop_harness.run:main"',
            self.pyproject,
        )
        self.assertTrue((_SRC / "desktop_harness" / "run.py").exists())

    def test_skill_md_packaged_as_data_with_frontmatter(self):
        self.assertIn(
            '"SKILL.md" = "desktop_harness/data/SKILL.md"',
            self.pyproject,
        )
        data_skill = _SRC / "desktop_harness" / "data" / "SKILL.md"
        self.assertTrue(data_skill.exists())
        text = data_skill.read_text()
        self.assertTrue(text.startswith("---"))
        self.assertIn("name: desktop-harness", text[:500])
        # repo-root SKILL.md also ships
        self.assertTrue((_ROOT / "SKILL.md").exists())

    def test_readme_status_matches_package_version(self):
        self.assertIn(f"v{self.version}", self.readme)

    def test_wheel_uses_src_layout(self):
        self.assertIn('packages = ["src/desktop_harness"]', self.pyproject)


if __name__ == "__main__":
    unittest.main()
