"""Pre-print readiness gate - a read-only glance at whether the printer is ready to start a print.

Queries Klipper's live objects and returns a list of translatable ``{code, level, ok, params}``
checks plus an overall ``ready`` flag. Read-only: it never actuates (the generated hard-blocking
PRINT_START preamble is a later step). The frontend renders ``preflight.checks.<code>``.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.moonraker_client import MoonrakerClient

#: Print states that mean a job is already running (can't start another).
_ACTIVE = ("printing", "paused")


def _check(code: str, ok: bool, level: str, **params: Any) -> dict[str, Any]:
    return {"code": code, "ok": ok, "level": level, "params": params}


async def preflight(moonraker_url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Returns ``{ready, checks}``. ``ready`` is True only when no check is a hard blocker
    (an ``error``-level failure); ``warn`` failures inform but don't block."""
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        objs = await client.query_objects(["webhooks", "print_stats", "toolhead"])
    except httpx.HTTPError:
        return {"ready": False, "checks": [_check("unreachable", False, "error")]}

    klippy_state = str((objs.get("webhooks") or {}).get("state", "") or "")
    print_state = str((objs.get("print_stats") or {}).get("state", "") or "")
    homed = str((objs.get("toolhead") or {}).get("homed_axes", "") or "")

    checks = [
        # Hard blocker: Klipper must be ready (not shutdown/startup/error).
        _check("klippy", klippy_state == "ready", "error", state=klippy_state or "unknown"),
        # Hard blocker: a job must not already be running.
        _check("idle", print_state not in _ACTIVE, "error", state=print_state or "standby"),
        # Informational: PRINT_START usually homes, so this only nudges.
        _check("homed", set("xyz") <= set(homed.lower()), "warn", axes=homed or "none"),
    ]
    ready = all(c["ok"] for c in checks if c["level"] == "error")
    return {"ready": ready, "checks": checks}
