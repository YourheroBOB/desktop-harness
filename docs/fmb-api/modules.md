# Python module reference

Import path root: `desktop_harness` (installed from `src/desktop_harness/`). macOS-only (pyobjc). Version: see `desktop_harness.__version__`.

---

## `desktop_harness.windows` — app/window discovery

### `list_apps() -> list[dict]`
Running apps with regular activation policy, sorted active-first then name. Item keys: `name`, `bundle_id`, `pid`, `active`, `hidden`. No parameters, does not raise on empty lists.

### `list_windows(on_screen_only: bool = True) -> list[dict]`
On-screen windows (layer-0, ≥50×50 pt). Item keys: `id`, `app`, `pid`, `title`, `x`, `y`, `w`, `h` (global screen points).

### `frontmost_app() -> dict | None`
Frontmost app info (`name`, `bundle_id`, `pid`, `active`, `hidden`), or `None`.

### `find_app(name_or_bundle: str | int) -> dict | None`
Match by name/bundle/pid. Resolution order: exact name or bundle → unique name prefix (shortest name wins on ties) → shortest-name substring → `NSRunningApplication` bundle-id lookup. `int` is treated as a pid; unknown pid → `None`.

### `activate(name_or_bundle: str, wait: float | None = None) -> dict`
Focus an app, launching via `open -a` (fallback `NSWorkspace`) if needed. `wait=None` → `0.35` cold / `0.12` warm; skips activation entirely if already frontmost; re-asserts activation up to ~1.2 s if focus is stolen. Audits `activate` / `activate_skip` / focus-uncertain cases.

**Errors:** `PermissionError` (sensitive app, see `safety.check_app_allowed`); `RuntimeError` (launch failure or unresolvable app).

### `open_app(name: str) -> dict`
Alias for `activate`.

---

## `desktop_harness.ax` — Accessibility tree

The primary "eyes" of the harness. Key public functions (also re-exported via `helpers`):

### `ax_snapshot(pid, max_nodes=…, interactive_only=True) -> list[dict]`
Snapshot of an app's AX nodes by pid. `interactive_only=True` restricts to interactive roles; `max_nodes` caps tree size (keep it small). Returns compact node dicts (`role`, `title`, `value`, `frame`, …).

**Example (from doctor):**

```python
nodes = ax_snapshot(front["pid"], max_nodes=20, interactive_only=True)
```

### `find(...)`
Label search with scoring (exact > prefix/partial; penalizes short-word false friends such as `Play` vs `Play all`). Returns the best node dict or `None`.

### `frame_on_screen(frame: dict) -> bool`
Filter helper: `True` only if a frame dict (`x`, `y`, `w`, `h`) is on-screen with positive size. Used to drop invisible/off-screen nodes before clicking.

**Example (from selftest):**

```python
frame_on_screen({"x": 100, "y": 100, "w": 50, "h": 50})   # True
frame_on_screen({"x": 100, "y": 9000, "w": 40, "h": 40})  # False
```

Element actions (`AXPress`, set value, point creation for coordinate fallback) live on this module's internal walk/press paths and are exposed through `helpers.click_text` / `helpers.set_field` — see [helpers.md](./helpers.md).

---

## `desktop_harness.capture` — pixel fallback

### `screenshot(app: str | None = None, window_id: int | None = None, path: str | Path | None = None) -> str`
Window-scoped (preferred) or main-display capture to PNG.

**Behavior:**

- `app` given → sensitive-app check on that name; window resolved by app/title substring (first match). No window → `RuntimeError`.
- Neither `app` nor `window_id` → main display; sensitive-**frontmost** check applies.
- `path=None` → unique per-call file (`capture-<pid>-<ns>.png`) under the harness temp dir.
- Audits every capture (`event: "screenshot"`).

**Errors:** `RuntimeError` (no window / empty capture / PNG encode failure), `PermissionError` (sensitive target).

### `window_info(app: str | None = None) -> dict | None`
First matching window dict (same shape as `windows.list_windows` items) for `app`, or the first window overall; `None` if nothing matches.

---

## `desktop_harness.input` — real mouse & keyboard (CGEvent)

All functions post real HID events; **Accessibility** permission required. These are mutations and are gated when a sensitive app is frontmost.

| Function | Signature |
|----------|-----------|
| `mouse_pos()` | `-> {"x": float, "y": float}` |
| `move_to(x, y, duration=…)` | animate to global coords |
| `move_by(dx, dy)` | relative nudge |
| `wiggle(amplitude=…, cycles=…, duration=…)` | pointer shake |
| `click(x, y, duration=…, double=False)` | move + left click |
| `right_click(x, y)` | move + right click |
| `drag(x1, y1, x2, y2)` | press-drag |
| `scroll(dy=…)` | wheel scroll |
| `type_text(text)` | unicode typing (~8 ms/char) |
| `hotkey(*keys)` | shortcut press |
| `key(…)` | single key press |

`DH_MOUSE_INSTANT=1` removes move animation. See [helpers.md](./helpers.md#mouse) for usage examples.

---

## `desktop_harness.presence` — agent cursor overlay

Cocoa accessory-app overlay: soft blue halo tracking the system cursor, red pulse on click, bottom "Agent controlling" banner. Default on (`DH_PRESENCE`).

Public functions (via `helpers`):

| Function | Description |
|----------|-------------|
| `enable_agent_cursor(enabled: bool)` | Show/hide the overlay |
| `hide_agent_presence()` | Tear down overlay at end of a sequence |
| `keep_alive()` | Pump the AppKit run loop during chunked waits — **must be called from the main thread**; never drive window methods from a background thread (AppKit SIGABRTs, see `docs/OBSERVE-LOOP.md`) |

---

## `desktop_harness.safety` — runtime gates

### `allow_sensitive() -> bool`
`True` only when the sensitive-override environment knob is set to an enabled value.

### `safe_mode() -> bool`
`True` unless explicitly disabled (default on). Safe mode is also agent **policy** documentation — no shell-escape helpers ship in the package.

### `check_app_allowed(name: str, bundle_id: str = "") -> None`
Raise `PermissionError` if `name`/`bundle_id` matches the sensitive substrings (password-manager-like names/bundles) and the override is not enabled. Called by `activate`/`open_app` and app-targeted `screenshot`.

### `check_frontmost_allowed() -> None`
Same gate for the **currently focused** app; used to block mutations (click/type/hotkey) and unscoped screenshots while a sensitive app is frontmost. Fails open only if the frontmost app cannot be read.

### `check_helper_allowed(name: str) -> None`
Hook for future high-risk helpers; currently blocks a frozen set of shell-escape names in safe mode (none ship today).

### `audit(event: str, detail: dict | None = None) -> None`
Append a JSON line to the audit log (path overridable, see [configuration.md](./configuration.md)). Never raises; swallows write errors.

### `CONFIRM_GUIDANCE`
Constant string: agents must stop and ask before send/post/purchase/delete/security/password actions.

---

## `desktop_harness.admin` — doctor

### `run_doctor() -> int`
Permission/health check chain (pyobjc → Accessibility → Screen Recording → live AX → window list). Prints `[PASS]`/`[FAIL]` lines and permission-pane hints on failure. Returns `0` (all pass) or `1`. See [cli.md](./cli.md#desktop-harness---doctor).

---

## `desktop_harness.selftest` — release self-test

### `run_selftest() -> int`
Non-destructive suite (doctor + core helpers + TextEdit open/type + daemon round-trip). Returns `0`/`1`. Details in [cli.md](./cli.md#desktop-harness-selftest).

---

## `desktop_harness.demo` — visible smoke test

### `run_demo() -> int`
Enables presence, opens TextEdit, moves/wiggles/clicks the real mouse, types a line, prints labels, hides presence. Always returns `0` on completion. See [cli.md](./cli.md#desktop-harness-demo).

---

## `desktop_harness.voice_tools` — voice tool schemas & executor

Realtime-compatible function-tool layer that maps voice intents onto helpers.

### `TOOL_DEFINITIONS: list[dict]`
OpenAI/xAI Realtime function-tool schemas: `list_apps`, `open_app`, `screen_labels`, `click_text`, `type_text`, `hotkey`, `move_mouse`, `click_xy`, `mouse_pos`, `wiggle_mouse`. Each entry has `type`, `name`, `description`, `parameters` (JSON-schema style, with `required` lists).

### `execute(name: str, arguments: dict | str, *, dry_run: bool = False) -> str`
Run one tool. `arguments` may be a dict or a JSON string (invalid JSON → error payload). Returns a JSON string for `function_call_output`: `{"ok": true, "result": …}` or `{"ok": false, "error": …}` (exceptions are caught and reported, never raised).

`dry_run=True` short-circuits: returns the would-be call without executing.

**Example:**

```python
from desktop_harness.voice_tools import execute
print(execute("mouse_pos", {}))
print(execute("move_mouse", '{"x": 400, "y": 300}', dry_run=True))
```

### `handlers(*, dry_run: bool = False) -> dict[str, Callable[..., str]]`
Map of tool name → `callable(**kwargs)` returning the same JSON strings.

### `SESSION_INSTRUCTIONS: str`
System prompt for the voice session (prefer labels/click_text over coordinates; confirm before destructive actions; keep replies short).

---

## `desktop_harness.run` — CLI entry

### `main()`
Console-script entry (`desktop-harness`). Parses the commands documented in [cli.md](./cli.md): script-from-stdin, `--doctor`, `--version`, `selftest`, `demo`, `skill`, `daemon start|status|stop`, `check-update`. Routes scripts through the daemon when one is running (unless disabled via environment knob).

---

## `agent-workspace/agent_helpers.py`

Agent-editable wrappers auto-loaded into every script and daemon namespace. Core primitives stay in `desktop_harness.helpers`; put task-specific composition (e.g. "open System Settings pane X, click Y") here.
