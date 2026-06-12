"""Printer-guard status — one poll for the shell's global "writes locked" awareness.

Combines the exclusive-slot state (which actuating operation is running, if any) with the live
print state, so the frontend learns *before* a refused write that the printer is printing or
that another tool currently owns the machine.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.services import printer_guard
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/guard", tags=["guard"])


@router.get("/status")
async def guard_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """The actuating slot + the live print state (``unknown`` when Moonraker is unreachable)."""
    out = printer_guard.status()
    try:
        objs = await MoonrakerClient(settings.moonraker_url).query_objects(["print_stats"])
        stats = objs.get("print_stats")
        stats = stats if isinstance(stats, dict) else {}
        out["print_state"] = str(stats.get("state", "unknown")).lower() or "unknown"
        out["reachable"] = True
    except httpx.HTTPError:
        out["print_state"] = "unknown"
        out["reachable"] = False
    return out
