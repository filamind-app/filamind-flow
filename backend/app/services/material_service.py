"""Material brain - the 'smart' layer over the stored filament profiles (material brain §12, PR 2).

The headline check: cross-reference a profile's max volumetric flow against the configured hotend's
ceiling (taken from the hardware catalog via ``max_flow_service.hotend_hint``), so a profile that
asks for more flow than the hotend can deliver is flagged BEFORE it shows up as under-extrusion.

Pure + testable; returns a translatable ``{code, level, params}`` verdict (frontend renders
``material.flowCheck.<code>``).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services import max_flow_service, printer_guard
from app.services.moonraker_client import MoonrakerClient


def _ceiling(hotend: str | None) -> tuple[float | None, str]:
    """Catalog ``expected_max_flow_mm3s`` for a hotend name (+ its canonical label), if known."""
    row = max_flow_service.hotend_hint(hotend)
    if not row:
        return None, (hotend or "")
    value = row.get("expected_max_flow_mm3s")
    label = str(row.get("name") or hotend or "")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value), label
    return None, label


def check_flow(material_flow: float, hotend: str | None) -> dict[str, Any]:
    """Verdict on whether ``material_flow`` (mm3/s) fits under the hotend's catalog ceiling.

    Codes: ``unset`` (no flow recorded) · ``no_ceiling`` (unknown hotend) ·
    ``exceeds`` (over the ceiling, warn) · ``within`` (ok, with % headroom).
    """
    if material_flow <= 0:
        return {"code": "unset", "level": "ok", "params": {}}
    ceiling, label = _ceiling(hotend)
    flow = round(material_flow, 1)
    if ceiling is None:
        return {"code": "no_ceiling", "level": "ok", "params": {"flow": flow}}
    if material_flow > ceiling:
        return {
            "code": "exceeds",
            "level": "warn",
            "params": {"flow": flow, "ceiling": round(ceiling, 1), "hotend": label},
        }
    return {
        "code": "within",
        "level": "ok",
        "params": {
            "flow": flow,
            "ceiling": round(ceiling, 1),
            "hotend": label,
            "headroom": round((1 - material_flow / ceiling) * 100),
        },
    }


async def apply_material(
    moonraker_url: str, profile: dict[str, Any], timeout: float = 20.0
) -> dict[str, Any]:
    """Preheat the printer to the profile's nozzle/bed temps via g-code (M104/M140).

    Gated like every write path: refuses while the printer is busy (printing / paused / error).
    Returns a translatable ``{ok, code, params}`` (frontend renders ``material.apply.<code>``).
    Only integer temps are interpolated into g-code - never arbitrary text.
    """
    nozzle = int(profile.get("nozzle_temp") or 0)
    bed = int(profile.get("bed_temp") or 0)
    commands: list[str] = []
    if nozzle > 0:
        commands.append(f"M104 S{nozzle}")
    if bed > 0:
        commands.append(f"M140 S{bed}")
    if not commands:
        return {"ok": False, "code": "no_temps", "params": {}}

    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await printer_guard.is_busy(client):
            return {"ok": False, "code": "busy", "params": {}}
        for cmd in commands:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return {"ok": False, "code": "moonraker_error", "params": {"error": str(exc)}}
    return {
        "ok": True,
        "code": "applied",
        "params": {"nozzle": nozzle, "bed": bed, "name": str(profile.get("name", ""))},
    }
