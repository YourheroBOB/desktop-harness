#!/usr/bin/env python3
"""AX-first edit example using only a temporary TextEdit document."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_PREFIX = "EXAMPLE_RESULT="
MARKER = "FAKE_VALUE_FOR_TEST"

HARNESS_SOURCE = r'''
import json
import os
import subprocess
from pathlib import Path

marker = "FAKE_VALUE_FOR_TEST"
path = Path(os.environ["DH_EXAMPLE_TEXT_FILE"])

launched = subprocess.run(
    ["open", "-a", "TextEdit", str(path)],
    capture_output=True,
    text=True,
    timeout=10,
    check=False,
)
if launched.returncode != 0:
    detail = (launched.stderr or launched.stdout or "unknown error").strip()
    raise RuntimeError(f"could not open temporary TextEdit file: {detail}")

wait(0.8)
activate("TextEdit", wait=0.25)
type_text(marker)
wait(0.8)

app = find_app("TextEdit")
if not app:
    raise RuntimeError("TextEdit was not found after opening the temporary file")

nodes = ax_snapshot(app["pid"], max_nodes=300)
serialized = json.dumps(nodes, ensure_ascii=False, default=str)
if marker not in serialized:
    raise RuntimeError("temporary marker was not visible in the Accessibility tree")

# Save and close only the temporary document that was just opened.
hotkey("cmd", "s")
wait(0.8)
hotkey("cmd", "w")
wait(0.4)

summary = {
    "ax_nodes_scanned": len(nodes),
    "marker_verified": True,
    "temporary_file_used": True,
}
print("EXAMPLE_RESULT=" + json.dumps(summary, sort_keys=True))
'''


def harness_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.is_file() else sys.executable


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dh-ax-example-") as temp_dir:
        text_file = Path(temp_dir) / "ax-edit.txt"
        text_file.write_text("", encoding="utf-8")

        env = os.environ.copy()
        env["DH_NO_DAEMON"] = "1"
        env["DH_PRESENCE"] = "0"
        env["DH_EXAMPLE_TEXT_FILE"] = str(text_file)
        env["DH_AUDIT_LOG"] = str(Path(temp_dir) / "audit.jsonl")
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
            timeout=45,
            check=False,
        )
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.returncode != 0:
            if completed.stderr:
                sys.stderr.write(completed.stderr)
            print("FAIL: AX edit verification did not complete", file=sys.stderr)
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
            print("FAIL: AX example result was not emitted", file=sys.stderr)
            return 1

        summary = json.loads(result_line[len(RESULT_PREFIX):])
        if summary.get("marker_verified") is not True:
            print("FAIL: AX marker was not verified", file=sys.stderr)
            return 1
        if MARKER not in text_file.read_text(encoding="utf-8"):
            print("FAIL: temporary file did not contain the fake marker", file=sys.stderr)
            return 1

        print("PASS: AX edit verification completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
