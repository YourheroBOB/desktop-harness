#!/usr/bin/env python3
"""Move the mouse a short distance and restore its original position."""
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
import math


def distance(left, right):
    return math.hypot(left["x"] - right["x"], left["y"] - right["y"])


before = mouse_pos()
move_to(before["x"] + 24, before["y"] + 18, duration=0.05)
moved = mouse_pos()
move_to(before["x"], before["y"], duration=0.05)
restored = mouse_pos()

moved_distance = distance(before, moved)
restored_distance = distance(before, restored)
if moved_distance < 5:
    raise RuntimeError("mouse did not move far enough for the example")
if restored_distance > 4:
    raise RuntimeError("mouse position was not restored accurately")

summary = {
    "distance_moved_px": round(moved_distance, 2),
    "restored": True,
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
    env["DH_MOUSE_INSTANT"] = "1"
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
        print("FAIL: mouse example did not complete", file=sys.stderr)
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
        print("FAIL: mouse example result was not emitted", file=sys.stderr)
        return 1

    summary = json.loads(result_line[len(RESULT_PREFIX):])
    if summary.get("restored") is not True:
        print("FAIL: mouse position was not restored", file=sys.stderr)
        return 1

    print("PASS: mouse position restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
