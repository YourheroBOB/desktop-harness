# CLI reference — `desktop-harness`

Entry point: `desktop_harness.run:main` (installed as the `desktop-harness` console script by `pyproject.toml`). The same behavior is available without installation via the repo dev launcher:

```bash
./desktop-harness <args>          # runs the working tree through .venv or python3
python3 -m desktop_harness.run <args>
```

All commands below accept the same arguments in both forms.

---

## `desktop-harness <<'PY' … PY` (script execution)

**Signature (shell):** `desktop-harness <<'PY'` … script … `PY`

Runs a Python script with every public helper (see [helpers.md](./helpers.md)) already in scope — no imports needed. If a warm daemon is running, the script is routed through it automatically; `DH_NO_DAEMON=1` forces a fresh in-process run.

**Parameters:** none (script text arrives on stdin).

**Returns:** script's stdout/stderr on the terminal; process exit code reflects script success.

**Errors:**

- Script exception → traceback printed, non-zero exit.
- Daemon route failure → falls back to in-process execution.
- Missing Accessibility/Screen Recording permission → AX/input/capture calls raise at runtime (run `--doctor` first).

**Example:**

```bash
desktop-harness <<'PY'
print(mouse_pos())
move_to(400, 300)
click(400, 300)
PY
```

---

## `desktop-harness --doctor`

Runs `admin.run_doctor()`. Checks, in order:

1. pyobjc frameworks importable (Quartz, AppKit, ApplicationServices)
2. Accessibility permission (`AXIsProcessTrusted`)
3. Screen Recording (writes a tiny PNG capture and checks its size)
4. Live AX snapshot of the frontmost app (must yield > 0 nodes)
5. Window list (must be non-empty)

**Returns / exit codes:** `0` all checks pass; `1` any check fails (the first failure is the one to fix — later checks often depend on it). On pyobjc import failure it prints a hint to install deps in the project venv and exits `1` immediately.

**Example:**

```bash
desktop-harness --doctor
```

---

## `desktop-harness --version`

Prints the package version (`desktop_harness.__version__`, currently matching `pyproject.toml`).

**Example:**

```bash
desktop-harness --version
```

---

## `desktop-harness selftest`

Runs `selftest.run_selftest()` — a **non-destructive** release-confidence suite:

- Full doctor pass
- Core helpers: `list_apps`, `list_windows`, `frontmost_app`, `labels`, `mouse_pos`, `move_to` (with restore), `screenshot`, `media_transport` API shape, `find_app` ranking + pid lookup, `frame_on_screen`
- Light GUI: opens TextEdit, types a token, verifies TextEdit has a window (window is left open)
- Daemon: `daemon start --bg`, exec round-trip, then quit

**Returns / exit codes:** `0` all pass; `1` any failure (count and name printed per check).

**Example:**

```bash
desktop-harness selftest
```

---

## `desktop-harness demo`

Runs `demo.run_demo()` — a **visible** smoke test: enables the agent cursor overlay, opens TextEdit, moves/wiggles/clicks the real mouse inside the TextEdit window, types a line, prints a labels sample, then hides the presence UI. TextEdit is left open.

**Returns / exit codes:** `0` on completion (watch the screen while it runs).

**Example:**

```bash
desktop-harness demo
```

---

## `desktop-harness skill`

Prints the agent skill markdown (`SKILL.md`, shipped as package data `desktop_harness/data/SKILL.md`) to stdout. Redirect it to register the skill for Grok Build.

**Errors:** if the packaged skill file cannot be located (e.g. broken install), file read fails — reinstall with `install.sh` or `pip install -e .`.

**Example:**

```bash
mkdir -p ~/.grok/skills/desktop-harness
desktop-harness skill > ~/.grok/skills/desktop-harness/SKILL.md
```

---

## `desktop-harness daemon start [--bg]`

Starts the warm daemon (`daemon.serve()`), which keeps Python/pyobjc loaded so subsequent CLI calls skip the cold start. See [daemon-protocol.md](./daemon-protocol.md) for socket path, token auth, and protocol.

**Parameters:**

| Flag | Effect |
|------|--------|
| `--bg` | Run in the background (used by `selftest` and recommended for agent sessions) |

**Errors:** `SystemExit` with a message if a daemon is already running (single-instance PID check); use `daemon stop` first.

**Example:**

```bash
desktop-harness daemon start --bg
```

---

## `desktop-harness daemon status`

Reports whether the daemon is up (socket exists and answers a token-authenticated `ping`).

**Example:**

```bash
desktop-harness daemon status
```

---

## `desktop-harness daemon stop`

Asks a running daemon to quit (`{"op":"quit"}`), removing socket and PID files.

**Example:**

```bash
desktop-harness daemon stop
```

---

## `desktop-harness check-update`

Compares the local install against the GitHub main branch (network call; optional, never automatic).

**Example:**

```bash
desktop-harness check-update
```
