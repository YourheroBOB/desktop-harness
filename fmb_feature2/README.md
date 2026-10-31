# fmb_feature2: Advanced AX Navigation, Polling & Workflow Helpers

This extension package implements the **secondary high-value capabilities** identified in `docs/PRE-RELEASE-REVIEW.md` (#12 Capability Gaps) and `DESIGN.md`:

1. **`menu_click(*menu_path, app=...)`**: Native Accessibility Menu Bar navigation (`AXMenuBar` -> `AXMenuItem` traversal and `AXPress`), replacing fragile coordinate clicks or keyboard shortcuts when selecting application menus.
2. **`wait_for(predicate_or_label, timeout=..., interval=...)`**: Predicate polling to eliminate fixed `sleep()` / `wait(0.5)` race conditions in automated multi-step agent interactions.
3. **`focus_window_by_title(title_query, app=...)`**: Precision window matching and raising (`AXRaise`), solving multi-window switching issues.
4. **`clipboard_get()`, `clipboard_set(text)`, `fast_paste(text)`**: High-speed bulk text insertion via system pasteboard + Cmd+V, bypassing per-character keystroke latency (`8ms/char`) and special character keycode mapping limitations.

---

## Architecture & Integration

All new logic is contained cleanly within `fmb_feature2/` to ensure zero disruption to existing repository files.

```
fmb_feature2/
├── advanced_helpers.py       # Core helpers with safety gate integration & PyObjC/fallback support
├── test_advanced_helpers.py  # Unit test suite (100% runnable in standalone or CI environment)
└── README.md                 # Integration manual & API specifications
```

### How to Integrate into Core Harness

There are two recommended ways to expose these helpers to agents:

#### Option A: Expose via Agent Workspace (Zero core modification)
Add the imports to `agent-workspace/agent_helpers.py`:
```python
from fmb_feature2.advanced_helpers import (
    menu_click,
    wait_for,
    focus_window_by_title,
    clipboard_get,
    clipboard_set,
    fast_paste,
)
```
Any script executed via `desktop-harness <<'PY'` automatically loads `agent_helpers.py` into the execution namespace.

#### Option B: Merge into Core Helpers (`src/desktop_harness/helpers.py`)
Import and re-export the helpers inside `src/desktop_harness/helpers.py` and register them in `namespace()`:
```python
from fmb_feature2.advanced_helpers import (
    menu_click,
    wait_for,
    focus_window_by_title,
    clipboard_get,
    clipboard_set,
    fast_paste,
)
__all__ += [
    "menu_click",
    "wait_for",
    "focus_window_by_title",
    "clipboard_get",
    "clipboard_set",
    "fast_paste",
]
```

---

## API Reference

### 1. `menu_click(*menu_path, app=None, timeout=3.0) -> bool`
Traverses the application's AX menu bar and clicks the menu action.
```python
# Saves the document in TextEdit
menu_click("File", "Save", app="TextEdit")

# Opens Format -> Font -> Show Fonts in the active app
menu_click("Format", "Font", "Show Fonts")
```

### 2. `wait_for(predicate_or_label, app=None, role=None, timeout=5.0, interval=0.1) -> Any`
Polls until an element appears or a custom predicate returns truthy.
```python
# Wait for button to appear:
save_btn = wait_for("Save", app="TextEdit", role="AXButton", timeout=3.0)

# Wait for custom condition:
dialog = wait_for(lambda: find("Confirm"), timeout=5.0)
```

### 3. `focus_window_by_title(title_query, app=None) -> dict`
Brings a specific window to the foreground by its window title.
```python
win = focus_window_by_title("Report-Q3.pdf", app="Preview")
print("Focused window id:", win["id"])
```

### 4. `fast_paste(text: str, restore_clipboard: bool = False) -> None`
Pastes large text or code snippets instantaneously via clipboard and `cmd+v`.
```python
code = """
def hello():
    print("Fast pasted without 8ms/char lag!")
"""
fast_paste(code, restore_clipboard=True)
```

---

## Running the Tests

To run the unit tests:

```bash
python3 -m unittest fmb_feature2/test_advanced_helpers.py
```
or with pytest:
```bash
pytest fmb_feature2/test_advanced_helpers.py -v
```
