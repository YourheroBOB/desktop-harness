"""Window / display capture — pixel fallback when AX is not enough."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import Quartz
from AppKit import NSBitmapImageRep, NSImage

from . import windows as winmod

TMP = Path(tempfile.gettempdir()) / "desktop-harness"
TMP.mkdir(exist_ok=True)


def _save_cgimage(image, path: Path) -> Path:
    if image is None:
        raise RuntimeError("capture returned no image")
    # Wrap CGImage in NSBitmapImageRep → PNG
    rep = NSBitmapImageRep.alloc().initWithCGImage_(image)
    data = rep.representationUsingType_properties_(
        4, None)  # NSBitmapImageFileTypePNG = 4
    if data is None:
        raise RuntimeError("failed to encode PNG")
    path = Path(path)
    path.write_bytes(bytes(data))
    return path


def _window_by_id(window_id: int) -> dict[str, Any] | None:
    for window in winmod.list_windows(on_screen_only=False):
        if int(window.get("id") or 0) == window_id:
            return window
    return None


def _window_identity(window: dict[str, Any]) -> tuple[str, str]:
    pid = int(window.get("pid") or 0)
    app_info = None
    if pid:
        try:
            app_info = winmod.find_app(pid)
        except Exception:
            app_info = None
    name = str((app_info or {}).get("name") or window.get("app") or "")
    bundle_id = str((app_info or {}).get("bundle_id") or "")
    return name, bundle_id


def _check_window_allowed(window: dict[str, Any]) -> None:
    from . import safety as _safety
    name, bundle_id = _window_identity(window)
    if not name and not bundle_id:
        raise PermissionError("refusing to capture a window with an unknown owner")
    _safety.check_app_allowed(name, bundle_id)


def screenshot(
    app: str | int | None = None,
    window_id: int | None = None,
    path: str | Path | None = None,
) -> str:
    """Capture a window (preferred) or the main display.

    Returns path to PNG. Prefer app/window scope over full desktop.
    """
    from . import safety as _safety

    app_info = None
    if app:
        app_info = winmod.find_app(app)
        _safety.check_app_allowed(app)

    if path is None:
        # Unique per call — concurrent agent steps (or two calls in the
        # same script) used to clobber a single shared capture.png.
        path = TMP / f"capture-{os.getpid()}-{time.time_ns()}.png"
    path = Path(path)

    if window_id is not None:
        target_window = _window_by_id(int(window_id))
        if target_window is None:
            raise RuntimeError(f"unknown on-screen window id {window_id!r}")
        _check_window_allowed(target_window)
        if app:
            if app_info is not None:
                target_pid = int(target_window.get("pid") or 0)
                app_pid = int(app_info.get("pid") or 0)
                if target_pid != app_pid:
                    raise RuntimeError("window_id does not belong to the requested app")
            elif isinstance(app, str):
                query = app.casefold()
                owner = str(target_window.get("app") or "").casefold()
                title = str(target_window.get("title") or "").casefold()
                if query not in owner and query not in title:
                    raise RuntimeError("window_id does not match the requested app")
            else:
                raise RuntimeError(f"unknown app {app!r}")
        wid = int(target_window["id"])
    elif app:
        if app_info is not None:
            app_pid = int(app_info.get("pid") or 0)
            candidates = [
                window for window in winmod.list_windows()
                if int(window.get("pid") or 0) == app_pid
            ]
        elif isinstance(app, str):
            query = app.casefold()
            candidates = [
                window for window in winmod.list_windows()
                if query in str(window.get("app") or "").casefold()
                or query in str(window.get("title") or "").casefold()
            ]
        else:
            candidates = []
        if not candidates:
            raise RuntimeError(f"no on-screen window for app={app!r}")
        target_window = candidates[0]
        _check_window_allowed(target_window)
        wid = int(target_window["id"])
    else:
        # An unscoped capture may expose a sensitive app that is frontmost.
        _safety.check_frontmost_allowed()
        wid = None
    if wid is not None:
        image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            wid,
            Quartz.kCGWindowImageBoundsIgnoreFraming
            | Quartz.kCGWindowImageNominalResolution,
        )
    else:
        # main display
        bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        image = Quartz.CGWindowListCreateImage(
            bounds,
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
            Quartz.kCGWindowImageNominalResolution,
        )
    _save_cgimage(image, path)
    _safety.audit("screenshot", {"app": app, "window_id": wid, "path": str(path)})
    return str(path)


def window_info(app: str | None = None) -> dict[str, Any] | None:
    if app:
        for w in winmod.list_windows():
            if app.lower() in w["app"].lower():
                return w
        return None
    wins = winmod.list_windows()
    return wins[0] if wins else None
