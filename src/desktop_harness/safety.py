"""Safety gates for real-desktop control.

Runtime blocks:
  - Opening / focusing apps with sensitive name or bundle substrings
    (unless DH_ALLOW_SENSITIVE=1)
  - Mutating actions while a sensitive app is frontmost
    (unless DH_ALLOW_SENSITIVE=1)

DH_SAFE=1 (default) is also agent policy documentation: no shell escape
helpers ship in this package.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_SENSITIVE_NAME_SUBSTR = (
    "1password", "bitwarden", "keychain", "lastpass", "keepass",
    "dashlane", "nordpass", "enpass", "secrets", "wallet", "bank",
)
_SENSITIVE_BUNDLE_SUBSTR = (
    "1password", "bitwarden", "keychain", "lastpass", "keepass",
    "dashlane", "nordpass", "enpass",
)

_AUDIT = Path(os.environ.get(
    "DH_AUDIT_LOG",
    Path.home() / ".desktop-harness" / "audit.jsonl",
))


def allow_sensitive() -> bool:
    return os.environ.get("DH_ALLOW_SENSITIVE", "").lower() in ("1", "true", "yes")


def safe_mode() -> bool:
    v = os.environ.get("DH_SAFE", "1").lower()
    return v not in ("0", "false", "no")


def _looks_sensitive(name: str = "", bundle_id: str = "") -> bool:
    low = (name or "").lower()
    bid = (bundle_id or "").lower()
    for s in _SENSITIVE_NAME_SUBSTR:
        if s in low:
            return True
    for s in _SENSITIVE_BUNDLE_SUBSTR:
        if s in bid:
            return True
    return False


def check_app_allowed(name: str | int, bundle_id: str = "") -> None:
    if allow_sensitive():
        return

    name_text = "" if name is None else str(name)
    if _looks_sensitive(name_text, bundle_id):
        raise PermissionError(
            f"refusing to control sensitive app {name_text!r} "
            f"({bundle_id or 'no bundle'}). "
            f"Set DH_ALLOW_SENSITIVE=1 if you really mean it."
        )
    if bundle_id:
        return

    # The supplied name may be an alias or partial title. Resolve it before
    # allowing access so an alias cannot bypass the sensitive-app gate.
    try:
        from . import windows as winmod
        resolved = winmod.find_app(name if isinstance(name, int) else name_text)
    except Exception as exc:
        raise PermissionError(
            "refusing to control an app: application lookup failed"
        ) from exc

    if resolved:
        actual_name = str(resolved.get("name") or name_text)
        actual_bundle = str(resolved.get("bundle_id") or "")
        if _looks_sensitive(actual_name, actual_bundle):
            raise PermissionError(
                f"refusing to control sensitive app {actual_name!r} "
                f"({actual_bundle or 'no bundle'}). "
                f"Set DH_ALLOW_SENSITIVE=1 if you really mean it."
            )


def check_frontmost_allowed() -> None:
    """Block mutations when a sensitive app is already focused."""
    if allow_sensitive():
        return
    try:
        from . import windows as winmod
        front = winmod.frontmost_app()
    except Exception as exc:
        raise PermissionError(
            "refusing mutation: unable to verify the frontmost application"
        ) from exc
    if not front:
        raise PermissionError(
            "refusing mutation: no frontmost application could be identified"
        )

    name = str(front.get("name") or "")
    bundle_id = str(front.get("bundle_id") or "")
    pid = front.get("pid")
    if not name and not bundle_id and pid:
        try:
            resolved = winmod.find_app(int(pid))
        except Exception:
            resolved = None
        if resolved:
            name = str(resolved.get("name") or "")
            bundle_id = str(resolved.get("bundle_id") or "")

    if not name and not bundle_id:
        raise PermissionError(
            "refusing mutation: frontmost application identity is unknown"
        )
    check_app_allowed(name, bundle_id)


def check_helper_allowed(name: str) -> None:
    # No high-risk shell helpers ship today; keep hook for future.
    blocked = frozenset({"run_shell", "shell", "osascript_raw"})
    if name in blocked and safe_mode() and not allow_sensitive():
        raise PermissionError(
            f"helper {name!r} blocked in safe mode (DH_SAFE=1)."
        )


def audit(event: str, detail: dict[str, Any] | None = None) -> None:
    try:
        _AUDIT.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(), "event": event, "detail": detail or {}}
        with _AUDIT.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


CONFIRM_GUIDANCE = (
    "Before sending messages, posting, purchasing, deleting data, changing "
    "security/privacy settings, or entering passwords: STOP and ask the user."
)
