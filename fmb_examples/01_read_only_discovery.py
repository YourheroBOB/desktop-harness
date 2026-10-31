#!/usr/bin/env python3
"""Read-only desktop-harness discovery example.

The helper output is intentionally reduced to counts so application names and
window titles are not disclosed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PREFIX = "EXAMPLE_RESULT="

HARNESS_SOURCE = r'''
import json

apps = list_apps()
windows = list_windows()
front = frontmost_app()
summary = {
    "apps": len(apps),
    "frontmost_detected": bool(front),
    "windows": len(windows),
}
print("EXAMPLE_RESULT=" + json.dumps(summary, sort_keys=True))
'''


def harness_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.is_file() else sys.executable


def main() -> int:
    env = os.environ.copy()
    env["DH_NO_DAEMON"] = "1"
    env["DH_PRESENCE"] = "0"
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + old_pythonpath if old_pythonpath else ""
    )

    completed = subprocess.run(
        [harness_python(), "-m", "desktop_harness.run"],
        input=HARNESS_SOURCE,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        timeout=30,
        check=False,
    )
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.returncode != 0:
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        print("FAIL: read-only discovery did not complete", file=sys.stderr)
        return completed.returncode

    result_line = next(
        (
            line
            for line in completed.stdout.splitlines()
            if line.startswith(RESULT_PREFIX)
        ),
        None,
    )
    if result_line is None:
        print("FAIL: discovery result was not emitted", file=sys.stderr)
        return 1

    summary = json.loads(result_line[len(RESULT_PREFIX):])
    if not isinstance(summary.get("apps"), int):
        print("FAIL: malformed discovery result", file=sys.stderr)
        return 1
    if not isinstance(summary.get("windows"), int):
        print("FAIL: malformed discovery result", file=sys.stderr)
        return 1
    if not isinstance(summary.get("frontmost_detected"), bool):
        print("FAIL: malformed discovery result", file=sys.stderr)
        return 1

    print("PASS: read-only discovery completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
