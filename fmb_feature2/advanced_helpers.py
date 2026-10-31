"""Advanced AX navigation, polling, and desktop workflow helpers for desktop-harness.

This module provides high-value helpers addressing capability gaps documented in
DESIGN.md and docs/PRE-RELEASE-REVIEW.md:
  1. menu_click(*menu_path, app=...): Native AX menu bar walk and trigger (e.g. ("File", "Save As...")).
  2. wait_for(condition, timeout=..., interval=...): Eliminate fixed sleep races by polling UI states.
  3. focus_window_by_title(title_query, app=...): Precision window targeting for multi-window workflows.
  4. clipboard_get(), clipboard_set(text), fast_paste(text): Efficient bulk text entry without per-character HID latency.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any, Callable

# Optional integration with existing desktop_harness modules
try:
    from desktop_harness import ax as _ax
    from desktop_harness import helpers as _helpers
    from desktop_harness import safety as _safety
    from desktop_harness import windows as _windows
except ImportError:  # pragma: no cover
    _ax = None
    _helpers = None
    _safety = None
    _windows = None

try:
    from AppKit import NSPasteboard, NSPasteboardTypeString
    import ApplicationServices
    _HAS_PYOBJC = True
except ImportError:  # pragma: no cover
    NSPasteboard = None
    NSPasteboardTypeString = None
    ApplicationServices = None
    _HAS_PYOBJC = False


# ---------------------------------------------------------------------------
# 1. Polling / Synchronization (Eliminate fixed sleep races)
# ---------------------------------------------------------------------------

def wait_for(
    predicate_or_label: str | Callable[[], Any],
    app: str | int | None = None,
    role: str | None = None,
    timeout: float = 5.0,
    interval: float = 0.1,
    description: str | None = None,
) -> Any:
    """Poll until a UI condition or element becomes truthy or matches.

    Args:
        predicate_or_label: Either a callable returning a truthy value when ready,
            or a string label to look up via ax.find().
        app: App name or PID if predicate_or_label is a string label.
        role: Expected AX role when matching by string label.
        timeout: Maximum seconds to poll.
        interval: Sleep duration between polling attempts.
        description: Custom label for error messages on timeout.

    Returns:
        The matched element or truthy value returned by the predicate.

    Raises:
        TimeoutError: If condition is not met within `timeout` seconds.
    """
    deadline = time.time() + max(0.01, timeout)
    desc = description or (
        f"element matching '{predicate_or_label}'"
        if isinstance(predicate_or_label, str)
        else "predicate condition"
    )

    while True:
        if isinstance(predicate_or_label, str):
            if _helpers is not None and hasattr(_helpers, "find"):
                res = _helpers.find(predicate_or_label, app=app, role=role)
            elif _ax is not None and hasattr(_ax, "find"):
                pid = None
                if isinstance(app, int):
                    pid = app
                elif app and _windows is not None and hasattr(_windows, "find_app"):
                    app_info = _windows.find_app(app)
                    pid = app_info.get("pid") if app_info else None
                res = _ax.find(predicate_or_label, pid=pid, role=role)
            else:
                res = None
        else:
            res = predicate_or_label()

        if res:
            return res

        if time.time() >= deadline:
            raise TimeoutError(f"wait_for timed out after {timeout:.2f}s waiting for {desc}")

        time.sleep(interval)


# ---------------------------------------------------------------------------
# 2. AX Menu Bar Walk & Trigger
# ---------------------------------------------------------------------------

def _get_ax_attribute(element: Any, attribute: str) -> Any:
    """Read an AX attribute safely via ApplicationServices."""
    if not _HAS_PYOBJC or element is None:
        return None
    err, val = ApplicationServices.AXUIElementCopyAttributeValue(element, attribute, None)
    if err == 0:
        return val
    return None


def _perform_ax_action(element: Any, action: str) -> bool:
    """Trigger an AX action safely via ApplicationServices."""
    if not _HAS_PYOBJC or element is None:
        return False
    err = ApplicationServices.AXUIElementPerformAction(element, action)
    return err == 0


def _match_menu_item(items: list[Any], query: str) -> Any | None:
    """Search items for title matching query (exact first, then case-insensitive)."""
    q = query.strip()
    q_low = q.lower()
    
    # 1. Exact match
    for item in items:
        title = _get_ax_attribute(item, "AXTitle") or ""
        if str(title).strip() == q:
            return item
            
    # 2. Case-insensitive exact match
    for item in items:
        title = _get_ax_attribute(item, "AXTitle") or ""
        if str(title).strip().lower() == q_low:
            return item

    # 3. Substring match
    for item in items:
        title = _get_ax_attribute(item, "AXTitle") or ""
        if q_low in str(title).strip().lower():
            return item

    return None


def menu_click(
    *menu_path: str,
    app: str | int | None = None,
    timeout: float = 3.0,
) -> bool:
    """Walk the macOS AXMenuBar hierarchy and trigger a menu action.

    Example:
        menu_click("File", "Save As...", app="TextEdit")
        menu_click("Edit", "Find", "Find Next")

    Args:
        *menu_path: Sequence of menu titles to traverse, e.g. "File", "Export", "PDF...".
        app: Target app name or PID. If None, targets the frontmost application.
        timeout: Maximum seconds allowed for submenus to unfold.

    Returns:
        True if the terminal action succeeded.

    Raises:
        ValueError: If menu_path is empty.
        LookupError: If a menu item along the path cannot be found.
        PermissionError: If target app is sensitive and not allowed.
    """
    if not menu_path:
        raise ValueError("menu_path must contain at least one item (e.g. 'File', 'Save')")

    target_app_name = None
    target_pid = None

    if app is not None:
        if isinstance(app, int):
            target_pid = app
        else:
            target_app_name = app
            if _windows is not None and hasattr(_windows, "find_app"):
                app_info = _windows.find_app(app)
                if app_info:
                    target_pid = app_info.get("pid")
                    target_app_name = app_info.get("name")
    else:
        if _windows is not None and hasattr(_windows, "frontmost_app"):
            front = _windows.frontmost_app()
            if front:
                target_pid = front.get("pid")
                target_app_name = front.get("name")

    if _safety is not None:
        if target_app_name:
            _safety.check_app_allowed(target_app_name)
        else:
            _safety.check_frontmost_allowed()

    if not _HAS_PYOBJC:
        raise RuntimeError("pyobjc ApplicationServices is required for menu_click on macOS")

    if not target_pid:
        raise RuntimeError("Could not resolve target app PID for menu_click")

    app_elem = ApplicationServices.AXUIElementCreateApplication(target_pid)
    menu_bar = _get_ax_attribute(app_elem, "AXMenuBar")
    if not menu_bar:
        raise LookupError(f"App PID {target_pid} does not have an AXMenuBar")

    current_parent = menu_bar
    for idx, segment in enumerate(menu_path):
        is_leaf = (idx == len(menu_path) - 1)
        children = _get_ax_attribute(current_parent, "AXChildren") or []
        item = _match_menu_item(list(children), segment)

        if not item:
            available = [
                str(_get_ax_attribute(c, "AXTitle") or "").strip()
                for c in children
                if _get_ax_attribute(c, "AXTitle")
            ]
            raise LookupError(
                f"Menu item '{segment}' not found at step {idx + 1}. Available: {available}"
            )

        if is_leaf:
            # Final item: trigger AXPress
            ok = _perform_ax_action(item, "AXPress")
            if not ok:
                ok = _perform_ax_action(item, "AXPick")
            if _safety is not None and hasattr(_safety, "audit"):
                _safety.audit("menu_click", {
                    "app": target_app_name or target_pid,
                    "path": list(menu_path),
                    "success": ok,
                })
            return ok
        else:
            # Intermediate item: open submenu if needed
            _perform_ax_action(item, "AXPress")
            deadline = time.time() + timeout
            next_parent = None
            while time.time() < deadline:
                submenus = _get_ax_attribute(item, "AXChildren") or []
                if submenus:
                    next_parent = submenus[0] if len(submenus) == 1 else item
                    break
                time.sleep(0.05)

            if not next_parent:
                next_parent = item
            current_parent = next_parent

    return False


# ---------------------------------------------------------------------------
# 3. Precision Window Focus
# ---------------------------------------------------------------------------

def focus_window_by_title(title_query: str, app: str | None = None) -> dict[str, Any]:
    """Find a window matching title_query and raise/activate it.

    Args:
        title_query: Substring or exact title of the window.
        app: Optional app name filter.

    Returns:
        Window dict with id, title, app, bounds.

    Raises:
        LookupError: If no matching window is found.
    """
    if _safety is not None:
        if app:
            _safety.check_app_allowed(app)
        else:
            _safety.check_frontmost_allowed()

    if _windows is None or not hasattr(_windows, "list_windows"):
        raise RuntimeError("desktop_harness.windows module is required for focus_window_by_title")

    q = title_query.strip().lower()
    windows = _windows.list_windows(on_screen_only=False)

    candidates = []
    for w in windows:
        if app and app.lower() not in w.get("app", "").lower():
            continue
        title = (w.get("title") or "").strip()
        title_low = title.lower()
        if not title:
            continue
        if title_low == q:
            score = 100
        elif title_low.startswith(q):
            score = 80
        elif q in title_low:
            score = 50
        else:
            continue
        candidates.append((score, len(title), w))

    if not candidates:
        available_titles = [w.get("title") for w in windows if w.get("title")]
        raise LookupError(
            f"No window found matching title '{title_query}'"
            + (f" for app '{app}'" if app else "")
            + f". Available titles: {available_titles[:10]}"
        )

    # Pick highest score, then shortest title
    candidates.sort(key=lambda x: (-x[0], x[1]))
    matched = candidates[0][2]

    # Bring parent app to front first
    app_name = matched.get("app")
    if app_name and _windows is not None and hasattr(_windows, "activate"):
        _windows.activate(app_name)

    # If pyobjc is available, trigger AXRaise on the window element
    pid = matched.get("pid")
    if _HAS_PYOBJC and pid:
        app_elem = ApplicationServices.AXUIElementCreateApplication(pid)
        ax_windows = _get_ax_attribute(app_elem, "AXWindows") or []
        for ax_w in ax_windows:
            w_title = _get_ax_attribute(ax_w, "AXTitle") or ""
            if q in str(w_title).lower():
                _perform_ax_action(ax_w, "AXRaise")
                break

    if _safety is not None and hasattr(_safety, "audit"):
        _safety.audit("focus_window_by_title", {
            "title_query": title_query,
            "matched_title": matched.get("title"),
            "window_id": matched.get("id"),
        })

    return matched


# ---------------------------------------------------------------------------
# 4. Clipboard & Fast Paste
# ---------------------------------------------------------------------------

def clipboard_get() -> str:
    """Retrieve current plain text from the macOS system pasteboard."""
    if _HAS_PYOBJC and NSPasteboard is not None:
        pb = NSPasteboard.generalPasteboard()
        val = pb.stringForType_(NSPasteboardTypeString)
        return str(val) if val is not None else ""

    # Fallback to pbpaste
    try:
        proc = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        return proc.stdout
    except Exception as e:
        raise RuntimeError(f"Failed to read clipboard via pbpaste: {e}") from e


def clipboard_set(text: str) -> None:
    """Set plain text content to the macOS system pasteboard."""
    if _HAS_PYOBJC and NSPasteboard is not None:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
        return

    # Fallback to pbcopy
    try:
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(input=text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"pbcopy returned non-zero code {proc.returncode}")
    except Exception as e:
        raise RuntimeError(f"Failed to set clipboard via pbcopy: {e}") from e


def fast_paste(text: str, restore_clipboard: bool = False) -> None:
    """Quickly paste text into the active field via Clipboard + Cmd+V.

    Avoids typing delays (e.g. 8ms/char) and unicode layout inconsistencies
    when pasting multi-line code or long paragraphs.

    Args:
        text: String to insert into the currently focused input.
        restore_clipboard: If True, preserves previous clipboard contents after paste.
    """
    if _safety is not None:
        _safety.check_frontmost_allowed()

    original = None
    if restore_clipboard:
        try:
            original = clipboard_get()
        except Exception:
            original = None

    clipboard_set(text)

    if _helpers is not None and hasattr(_helpers, "hotkey"):
        _helpers.hotkey("cmd", "v")
    else:
        # Fallback using osascript if helpers module not active
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=False,
        )

    if restore_clipboard and original is not None:
        time.sleep(0.08)
        try:
            clipboard_set(original)
        except Exception:
            pass

    if _safety is not None and hasattr(_safety, "audit"):
        _safety.audit("fast_paste", {"length": len(text)})
