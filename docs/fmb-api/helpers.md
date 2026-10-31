# Helper reference (script scope)

All functions below are pre-imported into every `desktop-harness <<'PY' … PY` script and into the daemon exec namespace. They are the public surface of `desktop_harness.helpers` (which re-exports primitives from `windows`, `ax`, `capture`, `input`, `presence`).

Task-specific wrappers can be added in `agent-workspace/agent_helpers.py`; they are auto-loaded into script scope alongside these.

---

## Discovery

### `list_apps()`

Running applications with a regular activation policy (agents/UI helpers skipped), sorted active-first then by name.

**Returns:** `list[dict]` — each item: `name` (str), `bundle_id` (str), `pid` (int), `active` (bool), `hidden` (bool).

**Example:**

```python
for a in list_apps():
    if a["active"]:
        print(a["name"], a["pid"])
```

### `list_windows(on_screen_only=True)`

On-screen windows with global-screen bounds.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `on_screen_only` | `bool` | `True` | If `False`, include off-screen windows |

**Returns:** `list[dict]` — each item: `id` (window id, int), `app` (owner name), `pid` (int), `title` (str), `x`, `y`, `w`, `h` (floats). Windows smaller than 50×50 pt or on non-zero layers (menus, Dock) are excluded.

**Example:**

```python
wins = [w for w in list_windows() if w["app"] == "TextEdit"]
```

### `frontmost_app()`

**Returns:** `dict | None` — the frontmost application (`name`, `bundle_id`, `pid`, `active: True`, `hidden`), or `None` if none can be resolved.

**Example:**

```python
print(frontmost_app())
```

### `find_app(name_or_bundle)`

Resolve an app by localized name, bundle id, or pid.

**Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `name_or_bundle` | `str \| int` | Name, bundle id, or pid. Match order: exact name/bundle → unique name prefix → best (shortest-name) substring → bundle-id lookup |

**Returns:** `dict | None` — same shape as `list_apps()` items; `None` if no match.

**Errors:** an `int` pid with no running process returns `None` (does not raise).

**Example:**

```python
info = find_app("TextEdit") or find_app("com.apple.TextEdit")
by_pid = find_app(frontmost_app()["pid"])
```

### `open_app(name)` / `activate(name, wait=None)`

Open (launch if needed) and focus an app. `open_app` is an alias for `activate`.

**Parameters (activate):**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | App name or bundle id |
| `wait` | `float \| None` | `None` | Seconds to settle after activation. `None` → `0.35` on cold launch, `0.12` if already running |

**Returns:** `dict` — resolved app info (best-effort; `warn: "focus_uncertain"` is audited if another app keeps stealing focus).

**Errors:**

- `PermissionError` — app name/bundle matches the sensitive list and `DH_ALLOW_SENSITIVE` is not enabled.
- `RuntimeError` — app not found and could not be launched, or launched but not resolvable within the poll window.

**Behavior:** if the app is already frontmost, activation and the settle sleep are skipped (audited as `activate_skip`).

**Example:**

```python
activate("Safari", wait=0.5)
open_app("System Settings")
```

---

## Seeing the UI (AX-first)

### `labels(app=None, limit=30)`

Readable Accessibility labels (fast, cheap — call this before any screenshot).

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `app` | `str \| None` | `None` | Scope to an app; `None` = frontmost |
| `limit` | `int` | `30` | Max labels returned |

**Returns:** `list[str]`.

**Example:**

```python
print(labels("TextEdit")[:8])
```

### `button_labels(...)`

Button-role labels only. Same scoping convention as `labels`; use it when you only care about actionable controls.

### `ax_snapshot(app_or_pid=None, max_nodes=..., interactive_only=True)`

Compact snapshot of interactive AX nodes.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `app_or_pid` | app name / pid / `None` | `None` | Target app; `None` = frontmost |
| `max_nodes` | `int` | module default | Cap on nodes walked/returned — keep it small; do not dump full trees |
| `interactive_only` | `bool` | `True` | Only interactive roles (buttons, fields, …) |

**Returns:** `list[dict]` — nodes with at least `role`, `title`, `value`, `frame` where available.

**Example:**

```python
nodes = ax_snapshot(max_nodes=40)
for n in nodes[:10]:
    print(n.get("role"), n.get("title"))
```

### `find(text, ...)`

Search the AX tree for a control matching `text` (exact matches score above partial ones; short-word false friends like `Play` vs `Play all` are penalized).

**Parameters:** text to match, plus optional app/role scoping (see `click_text`).

**Returns:** matching node dict (with `frame` for coordinate fallback) or `None` on miss.

**Example:**

```python
node = find("Save", app="TextEdit")
if node:
    print(node["frame"])
```

### `screenshot(app=None, window_id=None, path=None)`

Pixel fallback — capture a window (preferred) or the main display.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `app` | `str \| None` | `None` | Scope the capture to an app's window (matched by app/title substring) |
| `window_id` | `int \| None` | `None` | Explicit window id (from `list_windows`) |
| `path` | `str \| Path \| None` | `None` | Output PNG path. `None` → unique per-call path under the harness capture temp dir (concurrent calls never clobber each other) |

**Returns:** `str` — path to the written PNG.

**Errors:**

- `PermissionError` — targeted app is sensitive, or (unscoped capture) a sensitive app is frontmost, unless `DH_ALLOW_SENSITIVE` is enabled.
- `RuntimeError` — no on-screen window for `app`, or capture/encode failed.

**Example:**

```python
p = screenshot("TextEdit")
p = screenshot(window_id=list_windows()[0]["id"], path="/tmp/win.png")
```

---

## Acting on the UI

### `click_text(text, app=None, role=None, exact=False)`

Find a control by label and act on it — prefers the AX action path (`AXPress`/set value) over synthetic coordinate clicks.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | `str` | — | Label/title to match |
| `app` | `str \| int \| None` | `None` | Scope: app name or pid |
| `role` | `str \| None` | `None` | Restrict to an AX role, e.g. `"AXButton"` |
| `exact` | `bool` | `False` | Require an exact label match. Use `exact=True` for toggle-style labels like Play/Pause |

**Returns:** dict describing the pressed/clicked element (label + frame). A successful return means the AX call succeeded — **verify the resulting screen** (see `verify`).

**Errors:** `PermissionError` if a sensitive app is frontmost/targeted; raises on no match (a sample of nearby labels is included to help you recover).

**Example:**

```python
click_text("Format")
click_text("Play", role="AXButton", exact=True)   # never match "Play all"
```

### `set_field(...)`

Set a text field's value via AX (write the value directly instead of typing). Same scoping/safety semantics as `click_text`. Typed values are not written to the audit log.

### `type_text(text)`

Type unicode text into the focused field through the real keyboard (CGEvent). Character delay is small (~8 ms/char); for long text prefer clipboard + `hotkey("cmd", "v")`.

**Errors:** `PermissionError` if a sensitive app is frontmost.

**Example:**

```python
type_text("hello from the agent")
```

### `hotkey(*keys)`

Press a keyboard shortcut. Key names: `cmd`, `shift`, `alt`/`option`, `ctrl`, letters, `return`, `escape`, `space`, etc.

**Errors:** unknown key names raise (keycode map is incomplete for some punctuation/F-keys); `PermissionError` on sensitive frontmost app.

**Example:**

```python
hotkey("cmd", "s")
hotkey("cmd", "shift", "t")
```

### `key(...)`

Press a single key (same name conventions as `hotkey`).

---

## Mouse

All mouse functions drive the **real system cursor** (`CGWarpMouseCursorPosition` + `CGEventPost`). `duration` controls animation time; `DH_MOUSE_INSTANT=1` warps with no animation.

| Function | Signature | Description |
|----------|-----------|-------------|
| `mouse_pos` | `mouse_pos() -> dict` | Current pointer position: `{"x": float, "y": float}` |
| `move_to` | `move_to(x, y, duration=0.08) -> dict` | Animate pointer to global coordinates; returns resulting position |
| `move_by` | `move_by(dx, dy)` | Nudge the pointer by a delta |
| `wiggle` | `wiggle(amplitude=…, cycles=…, duration=…) -> dict` | Small shake at the pointer ("thinking" signal) |
| `click` | `click(x, y, duration=0.06, double=False)` | Move + left click (set `double=True` for double-click) |
| `right_click` | `right_click(x, y)` | Move + right (context-menu) click |
| `click_frame` | `click_frame(frame)` | Click the center of an AX node's `frame` dict (`x`, `y`, `w`, `h`) |
| `drag` | `drag(x1, y1, x2, y2)` | Press-drag from one point to another |
| `scroll` | `scroll(dy=…)` | Scroll wheel: positive/negative `dy` direction |

**Errors:** `PermissionError` if a sensitive app is frontmost (these are mutations). Coordinate clicks assume the target app is frontmost.

**Example:**

```python
p = mouse_pos()
move_to(400, 300, duration=0.2)
click(400, 300)
scroll(dy=-3)
```

---

## Media

### `media_transport(app=None)`

Read a media player's transport state **without acting**. Always look first; never toggle blindly.

**Parameters:** `app` (`str | None`) — optional app scope, default frontmost.

**Returns:** `dict` with:

| Key | Meaning |
|-----|---------|
| `state` | `"playing"`, `"paused"`, or `"unknown"` |
| `transport_play` | A transport-level **Play** control exists |
| `row_play` | A row/track-level Play exists (do **not** click this to resume) |
| `play` | Alias of `transport_play` (transport only — never row-level) |

**Example:**

```python
st = media_transport()
if st["state"] == "paused":
    ensure_media_playing()
```

### `ensure_media_playing(app=None)`

Look once, act once: if transport shows **Pause** (already playing) it is a no-op; if paused, presses the exact transport **Play** once. Never use `hotkey("space")` loops — Space toggles.

**Returns:** dict describing the state/act outcome.

---

## Presence (agent cursor UI)

On by default (`DH_PRESENCE=0` disables): one system cursor with a soft blue halo while moving, a brief red pulse on click, and a bottom "Agent controlling" banner.

| Function | Description |
|----------|-------------|
| `enable_agent_cursor(enabled: bool)` | Turn the overlay on/off |
| `hide_agent_presence()` | Hide the overlay when a control sequence ends |

**Example:**

```python
enable_agent_cursor(True)
# ... moves/clicks ...
hide_agent_presence()
```

---

## Meta / verification

| Function | Description |
|----------|-------------|
| `wait(seconds)` | Sleep helper |
| `wait_stable(...)` | Wait for the UI to settle (short default; used after presses) |
| `verify(note, app=None) -> str` | **Mandatory after screen-changing actions.** Captures a screenshot (and state) and returns the PNG path — read the image before claiming the step worked. Skip for pure discovery calls |
| `namespace() -> dict` | The full helper namespace as a dict (used by the daemon to build exec scope) |

**Example:**

```python
click_text("Save")
p = verify("Save sheet closed")
print(p)   # read this PNG with your vision tool
```
