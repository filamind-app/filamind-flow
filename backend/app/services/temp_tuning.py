"""Temperature tuning wizard - the third of the closed-loop tuning wizards.

Unlike Pressure Advance and retraction (a continuous TUNING_TOWER ramp), a temperature tower must
hold each temperature long enough for the hotend to settle, so it uses TUNING_TOWER's ``BAND`` mode:
the target is constant within each ``band`` mm and steps at every band boundary. Klipper evaluates
the band at its midpoint (``value = start + (floor(z/band)+0.5)*band*factor``), so the sample table
reports one temperature per band (with its Z range).

Planning is read-only; the apply is one gated ``SET_HEATER_TEMPERATURE`` (the same heating surface
the material preheat already uses). Returns a translatable ``{ok, code, params}`` on apply.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import httpx

from app.services import printer_guard
from app.services.moonraker_client import MoonrakerClient

#: Heaters a temperature tower may target (the value is interpolated into g-code, so allowlist it).
_HEATERS = ("extruder", "extruder1", "extruder2", "heater_bed")
_MIN_TEMP = 50.0
_MAX_TEMP = 350.0  # absolute apply ceiling; Klipper's own max_temp is the real per-printer guard
_MAX_BANDS = 60


@dataclass(frozen=True)
class TempTowerParams:
    start: float = 240.0  # temperature (C) at the base of the tower
    factor: float = -0.5  # C per mm of Z (negative descends up the tower)
    band: float = 10.0  # mm per constant-temperature band
    height: float = 100.0  # total tower height (mm)
    heater: str = "extruder"


def validate(p: TempTowerParams) -> None:
    if p.heater not in _HEATERS:
        raise ValueError("unknown heater")
    if not (_MIN_TEMP <= p.start <= _MAX_TEMP):
        raise ValueError("start out of range")
    if not (0 < abs(p.factor) <= 10):
        raise ValueError("factor out of range")
    if not (1 <= p.band <= 100):
        raise ValueError("band out of range")
    if not (0 < p.height <= 500):
        raise ValueError("height out of range")
    if math.ceil(p.height / p.band) > _MAX_BANDS:
        raise ValueError("too many bands")
    # Every band temperature must stay within the safe apply window.
    for _, _, temp in _bands(p):
        if not (_MIN_TEMP <= temp <= _MAX_TEMP):
            raise ValueError("band temperature out of range")


def temp_at_band(index: int, p: TempTowerParams) -> float:
    """The temperature TUNING_TOWER applies in band ``index`` (evaluated at the band midpoint)."""
    return round(p.start + (index + 0.5) * p.band * p.factor, 1)


def _bands(p: TempTowerParams) -> list[tuple[float, float, float]]:
    """``(z_low, z_high, temp)`` for each band the tower spans."""
    count = math.ceil(p.height / p.band)
    out: list[tuple[float, float, float]] = []
    for i in range(count):
        z_low = round(i * p.band, 1)
        z_high = round(min((i + 1) * p.band, p.height), 1)
        out.append((z_low, z_high, temp_at_band(i, p)))
    return out


def plan_tower(p: TempTowerParams) -> dict[str, Any]:
    """The TUNING_TOWER (BAND) command to run + a per-band (Z range -> temperature) table."""
    validate(p)
    command = (
        f"TUNING_TOWER COMMAND=SET_HEATER_TEMPERATURE HEATER={p.heater} PARAMETER=TARGET "
        f"START={p.start} FACTOR={p.factor} BAND={p.band}"
    )
    bands = [{"z_low": lo, "z_high": hi, "temp": t} for lo, hi, t in _bands(p)]
    return {
        "command": command,
        "start": p.start,
        "factor": p.factor,
        "band": p.band,
        "height": p.height,
        "heater": p.heater,
        "bands": bands,
    }


async def apply_temp(
    moonraker_url: str, heater: str, value: float, timeout: float = 10.0
) -> dict[str, Any]:
    """Set the chosen temperature live via ``SET_HEATER_TEMPERATURE``; gated (refused while busy).
    Only an allowlisted heater name and a bounded float are interpolated into g-code."""
    if heater not in _HEATERS:
        return {"ok": False, "code": "unknown_heater", "params": {}}
    if not (0 <= value <= _MAX_TEMP):
        return {"ok": False, "code": "out_of_range", "params": {"max": _MAX_TEMP}}
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await printer_guard.is_busy(client):
            return {"ok": False, "code": "busy", "params": {}}
        await client.run_gcode(f"SET_HEATER_TEMPERATURE HEATER={heater} TARGET={round(value, 1)}")
    except httpx.HTTPError as exc:
        return {"ok": False, "code": "moonraker_error", "params": {"error": str(exc)}}
    return {"ok": True, "code": "applied", "params": {"value": round(value, 1), "heater": heater}}
