"""Flow (extrusion) tuning wizard - the fourth tuning wizard, a guided calculator.

Klipper has no live flow override (unlike PA / retraction / temperature), so extrusion is
calibrated by commanding a known length, measuring what actually came out, and correcting the
extruder's ``rotation_distance``::

    new_rotation_distance = current_rotation_distance * (measured / requested)

The new value goes in ``printer.cfg`` and needs ``SAVE_CONFIG`` + a restart (it is not
live-settable), so this wizard never actuates: it reads the current ``rotation_distance`` and
computes the correction for the operator to paste.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.moonraker_client import MoonrakerClient


def compute(requested: float, measured: float, current_rotation_distance: float) -> dict[str, Any]:
    """Klipper extruder calibration: new rotation_distance + the equivalent slicer flow percent.

    Raises:
        ValueError: if any input is not positive.
    """
    if requested <= 0 or measured <= 0 or current_rotation_distance <= 0:
        raise ValueError("inputs must be positive")
    new_rd = round(current_rotation_distance * measured / requested, 5)
    flow_percent = round(requested / measured * 100, 1)
    return {"new_rotation_distance": new_rd, "flow_percent": flow_percent}


async def extruder_rotation_distance(moonraker_url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Read the live ``[extruder]`` ``rotation_distance`` (``None`` if unavailable)."""
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        data = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return {"rotation_distance": None}
    configfile = data.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    extruder = settings.get("extruder") if isinstance(settings, dict) else None
    rd = extruder.get("rotation_distance") if isinstance(extruder, dict) else None
    return {"rotation_distance": float(rd) if isinstance(rd, (int, float)) else None}
