# Repo scripts reference

Standalone scripts shipped in the repo (outside the installed package). Experimental/optional surfaces are marked.

---

## `scripts/voice_session.py` (experimental — voice control)

Grok Voice Realtime (speech-to-speech over WebSocket) → `desktop_harness.voice_tools` function calls → harness helpers.

**Requirements:** `XAI_API_KEY` in the environment (from the xAI console — **not** the Grok Build login), plus `websockets` (and later `sounddevice`/`numpy` for mic streaming) installed in the project venv. Mic streaming is scaffolded but not wired; use `--text` for tool-using turns today.

### Usage

```bash
python scripts/voice_session.py --list-tools
python scripts/voice_session.py --dry-run              # no key needed: local tool demo
python scripts/voice_session.py --dry-run --text "Open Safari"
python scripts/voice_session.py --text "Open TextEdit and type hello"
python scripts/voice_session.py                        # full duplex (needs key + mic)
```

### Arguments

| Arg | Effect |
|-----|--------|
| `--dry-run` | Print tool calls without executing real GUI actions. Without a key, runs a read-only local demo of the tool executor |
| `--text TEXT` | One-shot text turn (no mic) |
| `--list-tools` | Print each tool name + description and exit |

### Exit codes / errors

| Code | Condition |
|------|-----------|
| `0` | Normal completion |
| `1` | `websockets` not installed |
| `2` | Missing `XAI_API_KEY` and not `--dry-run` (prints setup guidance; never invents access) |

### Behavior

Connects to the Realtime endpoint, sends a `session.update` with `SESSION_INSTRUCTIONS` + `TOOL_DEFINITIONS`, streams text turns, and for each `response.function_call_arguments.done` event executes the tool via `voice_tools.execute` and returns a `function_call_output` item. Session instructions enforce voice confirmation before destructive actions.

---

## `scripts/observe-demo.sh` (visual QA loop)

Dense observe loop: captures ~24 full-screen frames (~0.28 s apart) while a harness script sweeps, squares, and clicks the mouse with the presence overlay on. Used to prove motion/focus bugs in the presence UI (see `docs/OBSERVE-LOOP.md`).

### Usage

```bash
./scripts/observe-demo.sh [OUT_DIR]     # default OUT_DIR: /tmp/dh-observe
```

### Arguments

| Arg | Effect |
|-----|--------|
| `OUT_DIR` (positional, optional) | Output directory for numbered PNG frames; cleared of `*.png` first |

**Behavior:** exports `DH_NO_DAEMON=1` and `DH_PRESENCE=1`, starts the capture loop in the background, runs the harness demo sequence (agent cursor on, hold, sweep, square, two clicks, `hide_agent_presence()`), waits for captures, then prints the frame count and first filenames. Read **multiple** frames (hold, mid-move, after-click, idle) before drawing conclusions.

---

## `install.sh` (one-shot installer)

```bash
chmod +x install.sh && ./install.sh
```

**Behavior (in order):**

1. Creates/uses `.venv` in the repo and installs pyobjc frameworks + the package (`pip install -e . --no-deps`)
2. Writes the `~/.local/bin/desktop-harness` shim and makes it (and the dev launcher) executable
3. If `~/.grok` exists, registers the Grok Build skill via `desktop-harness skill`
4. Prints the permission-grant and PATH instructions
5. Runs `desktop-harness --doctor` (non-fatal)

No arguments. Requires macOS + Python 3.10+. Re-run after `git pull` to refresh.

---

## `./desktop-harness` (dev launcher)

Runs the working tree without installing: picks `.venv/bin/python` if present (else `python3`), sets `PYTHONPATH` to `src/`, and execs `python -m desktop_harness.run "$@"`. Accepts all CLI arguments from [cli.md](./cli.md).
